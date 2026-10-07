"""Workspace discovery, package resources and bounded filesystem writes."""
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
import os
import tempfile

ROLES = ('architect', 'coder', 'tester', 'reviewer', 'perfs', 'docs')
DIRECTORIES = ('roles', 'work', 'knowledge', 'knowledge/decisions',
               'knowledge/notes', 'knowledge/reports')


class AgenceError(Exception):
    """Expected operational failure, displayed without a traceback."""


@dataclass(frozen=True)
class Workspace:
    root: Path

    @property
    def data(self):
        return self.root / '.agence'

    @property
    def source_root(self):
        for parent in (self.root, *self.root.parents):
            marker = parent / '.git'
            if marker.is_dir() and (marker / 'HEAD').is_file():
                return parent
            if marker.is_file() and marker.read_text(encoding='utf-8').startswith('gitdir:'):
                return parent
        return self.root

    @property
    def roles(self):
        directory = self.data / 'roles'
        return {p.stem for p in directory.glob('*.md') if p.is_file()}

    def bounded(self, path):
        path = Path(path)
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise AgenceError(f'{path}: managed destination escapes workspace')
        # Check every component: a symlink resolving inside today could be
        # retargeted between checks and writes. Managed writes reject symlinks.
        relative = path.relative_to(self.root)
        current = self.root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise AgenceError(f'{current}: symlinked managed destination')
        return path

    @contextmanager
    def lock(self):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.bounded(self.root / '.agence.lock')
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise AgenceError(f'{path}: workspace is locked; inspect the holder before removing the lock') from exc
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(f'{os.getpid()}\n')
            yield
        finally:
            path.unlink()

    def create(self, path, content):
        with self.bounded(path).open('x', encoding='utf-8') as stream:
            stream.write(content)

    def publish_index(self, content):
        target = self.bounded(self.data / 'INDEX.md')
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                             dir=target.parent, prefix='.INDEX-',
                                             delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def template(name):
    return files('agence').joinpath('templates', name).read_text(encoding='utf-8')


def explicit_workspace(path):
    path = Path(path).absolute()
    if path.name == '.agence':
        path = path.parent
    return Workspace(path)


def discover(root=None, start=None):
    if root is not None:
        workspace = explicit_workspace(root)
        if not workspace.data.is_dir():
            raise AgenceError(f'{workspace.data}: no initialized workspace')
        return workspace
    start = Path(start or Path.cwd()).absolute()
    if start.is_file():
        start = start.parent
    for candidate in (start, *start.parents):
        if candidate.name == '.agence' and candidate.is_dir():
            return Workspace(candidate.parent)
        if (candidate / '.agence').is_dir():
            return Workspace(candidate)
    raise AgenceError(f'{start}: no .agence workspace found; run ta setup')
