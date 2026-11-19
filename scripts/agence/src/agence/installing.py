"""Install standalone Codex agent definitions without changing user config."""
from pathlib import Path
import os
import tempfile

from .workspace import AgenceError


def install_agents(source, codex_dir, dry_run=False, force_run=False):
    source = Path(source).expanduser().absolute()
    codex_dir = Path(codex_dir).expanduser().absolute()
    destination = codex_dir / 'agents'
    if not source.is_dir():
        raise AgenceError(f'{source}: agent source directory does not exist')
    sources = sorted(source.glob('*.toml'))
    if not sources:
        raise AgenceError(f'{source}: no .toml agent definitions found')
    for directory in (codex_dir, destination):
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            raise AgenceError(f'{directory}: expected a directory, not a symlink or file')
    pending, unchanged = [], []
    # Read and preflight every input before creating directories or files.
    for path in sources:
        if path.is_symlink() or not path.is_file():
            raise AgenceError(f'{path}: agent definition must be a regular file')
        content = path.read_bytes()
        target = destination / path.name
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise AgenceError(f'{target}: incompatible existing destination')
        if target.exists():
            if target.read_bytes() == content:
                unchanged.append(target)
                continue
            if not force_run:
                raise AgenceError(f'{target}: existing agent differs; no files installed; use --force to replace it')
            pending.append((target, content, True))
        else:
            pending.append((target, content, False))
    if dry_run:
        return ''.join(f'Would {"replace" if replacing else "install"} {path}\n'
                       for path, _, replacing in pending) + ''.join(
            f'Unchanged {path}\n' for path in unchanged)
    created, replaced = [], []
    try:
        if pending:
            destination.mkdir(parents=True, exist_ok=True)
        for target, content, _ in pending:
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=destination, prefix='.ta-install-', delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                if force_run:
                    # Recheck after staging: force authorizes replacing regular
                    # files, never symlinks or directories. Atomic replacement
                    # preserves the previous file if publication fails.
                    if target.is_symlink() or (target.exists() and not target.is_file()):
                        raise AgenceError(f'{target}: incompatible destination during installation')
                    existed = target.exists()
                    os.replace(temporary, target)
                    (replaced if existed else created).append(target)
                    continue
                # Publish complete bytes exclusively, including under concurrent
                # installs. A competing file is never replaced.
                try:
                    os.link(temporary, target)
                except FileExistsError:
                    if target.is_symlink() or not target.is_file() or target.read_bytes() != content:
                        raise AgenceError(f'{target}: destination changed during installation')
                    unchanged.append(target)
                else:
                    created.append(target)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
    except (OSError, AgenceError, KeyboardInterrupt) as exc:
        installed = ', '.join(map(str, created)) or 'none'
        updated = ', '.join(map(str, replaced)) or 'none'
        raise AgenceError(f'Installation incomplete: {exc}\nInstalled: {installed}. Replaced: {updated}. Completed changes retained; fix the cause and retry ta install'
                          + (' --force.' if force_run else '.')) from exc
    return ''.join(f'Installed {path}\n' for path in created) + ''.join(
        f'Replaced {path}\n' for path in replaced) + ''.join(
        f'Unchanged {path}\n' for path in unchanged)
