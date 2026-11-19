"""Command orchestration using shared catalogs and bounded mutations."""
from pathlib import Path
import yaml

from .checks import check_directory, check_references
from .documents import Diagnostic, SPECS, catalog, parse, slug
from .rendering import render_index, render_status
from .workspace import (AgenceError, DIRECTORIES, ROLES, discover,
                        explicit_workspace, template)


def require_valid(diagnostics, relative_to=None):
    if diagnostics:
        raise AgenceError('\n'.join(d.format(relative_to) for d in sorted(diagnostics, key=lambda d: (str(d.path), d.code, d.message))))


def checked_catalog(workspace):
    result = catalog(workspace)
    require_valid(result.diagnostics)
    return result


def generate(workspace):
    result = checked_catalog(workspace)
    workspace.publish_index(render_index(workspace, result.documents))


def setup(args):
    workspace = explicit_workspace(args.path or args.root or Path.cwd())
    if args.path and args.root and workspace.root.resolve() != explicit_workspace(args.root).root.resolve():
        raise AgenceError('setup PATH and --root must select the same target')
    destinations = {workspace.root / 'AGENTS.md': template('AGENTS.md')}
    destinations.update({workspace.data / 'roles' / f'{r}.md': template(f'roles/{r}.md') for r in ROLES})
    directories = [workspace.data, *(workspace.data / p for p in DIRECTORIES)]
    # Preflight before creating the target or any files, including parent collisions.
    for path in [workspace.root, *directories, *destinations, workspace.data / 'INDEX.md']:
        workspace.bounded(path)
        for parent in path.parents:
            if parent.exists() and not parent.is_dir():
                raise AgenceError(f'{parent}: incompatible parent file')
            if parent == workspace.root:
                break
        if path.exists() and ((path in directories or path == workspace.root) != path.is_dir()):
            raise AgenceError(f'{path}: incompatible file/directory collision')
    created = []
    existing_rules = (workspace.root / 'AGENTS.md').exists()
    try:
        with workspace.lock():
            for directory in directories:
                if not directory.exists():
                    directory.mkdir()
                    created.append(str(directory))
            for path, content in destinations.items():
                if not path.exists():
                    workspace.create(path, content)
                    created.append(str(path))
            generate(workspace)
    except (OSError, AgenceError, KeyboardInterrupt) as exc:
        raise AgenceError(f'{exc}\nSetup incomplete. Created: {", ".join(created) or "nothing"}. Fix the reported destination/catalog and retry ta setup.') from exc
    notice = ''
    if existing_rules and 'Generated index ownership' not in (workspace.root / 'AGENTS.md').read_text(encoding='utf-8'):
        notice = '\nExisting AGENTS.md preserved; update its index instructions to use ta index.'
    return f'Initialized {workspace.root}\n' + '\n'.join(created) + notice + '\n'


def check(args):
    target = Path(args.path).absolute() if args.path else None
    directory_target = target is not None and target.is_dir()
    if args.check_kind == 'file' and not directory_target:
        try:
            workspace = discover(args.root, start=target)
        except AgenceError:
            if args.root:
                raise
            workspace = None
        _, diagnostics = parse(target, workspace)
    else:
        # Each check accepts a workspace directory or its .agence directory.
        # File checks also retain standalone single-document validation.
        file_target = target is not None and not directory_target and (
            target.is_file() or target.suffix.lower() == '.md')
        if target and not file_target:
            workspace = explicit_workspace(target)
        else:
            workspace = discover(args.root, start=target)
        diagnostics = []
        if args.check_kind in ('file', 'refs') and not workspace.data.is_dir():
            diagnostics.append(Diagnostic(workspace.data, 'layout', 'no initialized workspace'))
        if args.check_kind in ('dir', 'all'):
            diagnostics.extend(check_directory(workspace))
        if args.check_kind in ('file', 'refs', 'all'):
            result = catalog(workspace)
            diagnostics.extend(result.diagnostics)
            documents = result.documents
            if file_target:
                document, errors = parse(target, workspace)
                diagnostics.extend(errors)
                documents = [document] if document else []
            if args.check_kind in ('refs', 'all'):
                for document in documents:
                    diagnostics.extend(check_references(document, workspace, result))
    base = workspace.data if workspace is not None else Path.cwd()
    require_valid(list(set(diagnostics)), relative_to=base)
    return 'Checks passed.\n'


def new(args):
    workspace = discover(args.root)
    prefix, directory, statuses, _ = SPECS[args.document_kind]
    chosen_status = args.status or statuses[0]
    if chosen_status not in statuses:
        raise AgenceError(f'invalid {args.document_kind} status: {chosen_status}; choose {", ".join(statuses)}')
    if any(not value.strip() for value in args.tag):
        raise AgenceError('tags must be nonempty strings')
    title = args.title.strip()
    name = slug(title)
    if not name:
        raise AgenceError('title must contain characters usable in an ASCII slug')
    with workspace.lock():
        require_valid(check_directory(workspace))
        result = checked_catalog(workspace)
        if args.document_kind == 'work' and args.owner not in workspace.roles:
            raise AgenceError(f'no installed role: {args.owner}')
        for value in args.related:
            if len(result.resolve(value)) != 1:
                raise AgenceError(f'{value}: related ID must resolve to exactly one document')
        numbers = [int(d.id[2:]) for d in result.documents if d.id.startswith(prefix + '-')]
        doc_id = f'{prefix}-{max(numbers, default=0)+1:03d}'
        path = workspace.data / directory / f'{doc_id}-{name}.md'
        metadata = {'schema': f'agence/{args.document_kind}/v1', 'id': doc_id,
                    'title': title, 'status': chosen_status}
        if args.document_kind == 'work':
            metadata['owner'] = args.owner
        metadata.update(tags=args.tag, related=args.related)
        content = '---\n' + yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True) + '---\n\n'
        # User titles cannot introduce extra Markdown structure.
        from .rendering import escape
        content += '# ' + escape(title) + '\n' + template(args.document_kind + '.md')
        workspace.create(path, content)
        try:
            generate(workspace)
        except (OSError, AgenceError, KeyboardInterrupt) as exc:
            raise AgenceError(f'Created {path}, but index refresh failed: {exc}\nDocument retained; fix the cause and run ta index.') from exc
    return str(path) + '\n'


def index(args):
    workspace = discover(args.root)
    with workspace.lock():
        require_valid([d for d in check_directory(workspace) if d.path != workspace.data / 'INDEX.md'])
        generate(workspace)
    return str(workspace.data / 'INDEX.md') + '\n'


def status(args):
    workspace = discover(args.root)
    result = checked_catalog(workspace)
    selected = None
    if args.selection:
        matches = result.resolve(args.selection)
        if not matches:
            path = Path(args.selection).absolute()
            matches = [d for d in result.documents if d.path.resolve() == path.resolve()]
        if len(matches) != 1:
            raise AgenceError(f'{args.selection}: unknown or ambiguous document selection')
        selected = matches[0]
    return render_status(workspace, result.documents, selected)


def install(args):
    from .installing import install_agents
    return install_agents(args.source, args.codex_dir or Path.home() / '.codex', args.dry_run, getattr(args, 'force_run', False))
