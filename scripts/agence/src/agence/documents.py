"""Shared schema rules, safe frontmatter parsing and live document catalog."""
from dataclasses import dataclass, field
from pathlib import Path
import re
import os
import unicodedata
import yaml

from .workspace import DIRECTORIES

SPECS = {
    'work': ('T', 'work', ('planned', 'active', 'blocked', 'review', 'completed', 'cancelled'),
             ('Goal', 'Constraints', 'Context', 'Current state', 'Activity')),
    'decision': ('D', 'knowledge/decisions', ('proposed', 'accepted', 'rejected', 'deprecated', 'superseded'),
                 ('Decision', 'Rationale', 'Consequences', 'References')),
    'note': ('N', 'knowledge/notes', ('draft', 'current', 'outdated', 'superseded'), ('Summary',)),
    'report': ('R', 'knowledge/reports', ('draft', 'final', 'obsolete'), ()),
}
ID = re.compile(r'[TDNR]-[0-9]{3,}\Z')
NAME = re.compile(r'([TDNR]-[0-9]{3,})-([a-z0-9]+(?:-[a-z0-9]+)*)\.md\Z')


@dataclass(frozen=True)
class Diagnostic:
    path: Path
    code: str
    message: str
    line: int | None = None

    def format(self, relative_to=None):
        path = str(self.path) if relative_to is None else os.path.relpath(self.path, relative_to)
        location = path + (f':{self.line}' if self.line else '')
        message = self.message.replace(str(self.path), path) if relative_to is not None else self.message
        return f'{location}: {self.code}: {message}'

    def __str__(self):
        return self.format()


@dataclass
class Document:
    path: Path
    metadata: dict
    body: str
    kind: str | None
    activity: list = field(default_factory=list)

    @property
    def id(self):
        return self.metadata.get('id')


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            if key in result:
                raise yaml.constructor.ConstructorError(None, None,
                    f'duplicate YAML key: {key}', key_node.start_mark)
            result[key] = loader.construct_object(value_node, deep=deep)
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(None, None,
                'mapping key must be hashable', key_node.start_mark) from exc
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def prose(text):
    """Strip fenced examples, preserving newlines for source diagnostics."""
    fence = None
    result = []
    for line in text.splitlines(keepends=True):
        match = re.match(r'^\s{0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= len(fence) and not match[2].strip():
                fence = None
            result.append('\n' if line.endswith('\n') else '')
        elif match:
            fence = match[1]
            result.append('\n' if line.endswith('\n') else '')
        else:
            result.append(line)
    return ''.join(result)


def parse(path, workspace=None):
    path = Path(path)
    diagnostics = []
    def issue(code, message, line=None):
        diagnostics.append(Diagnostic(path, code, message, line))
    try:
        text = path.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as exc:
        issue('read', str(exc))
        return None, diagnostics
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != '---':
        issue('frontmatter', 'expected opening --- delimiter', 1)
        return None, diagnostics
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == '---'), None)
    if end is None:
        issue('frontmatter', 'missing closing --- delimiter', 1)
        return None, diagnostics
    try:
        metadata = yaml.load(''.join(lines[1:end]), Loader=UniqueLoader)
    except (yaml.YAMLError, ValueError, OverflowError) as exc:
        mark = getattr(exc, 'problem_mark', None)
        issue('yaml', str(exc), mark.line + 2 if mark else None)
        return None, diagnostics
    if not isinstance(metadata, dict):
        issue('metadata', 'frontmatter must be a mapping')
        return None, diagnostics
    body = ''.join(lines[end+1:])
    schema = metadata.get('schema')
    kind = next((k for k in SPECS if schema == f'agence/{k}/v1'), None)
    if kind is None:
        issue('schema', 'expected agence/<work|decision|note|report>/v1')
    match = NAME.fullmatch(path.name)
    if not match:
        issue('filename', 'expected PREFIX-NNN-lowercase-slug.md')
    doc_id = metadata.get('id')
    if not isinstance(doc_id, str) or not ID.fullmatch(doc_id):
        issue('id', 'expected T/D/N/R followed by at least three decimal digits')
    elif match and match[1] != doc_id:
        issue('id', 'filename ID does not match metadata ID')
    title = metadata.get('title')
    if not isinstance(title, str) or not title.strip():
        issue('title', 'title must be a nonempty string')
    for key in ('tags', 'related'):
        value = metadata.get(key)
        if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
            issue(key, f'{key} must be a list of nonempty strings')
        elif key == 'related' and any(not ID.fullmatch(v) for v in value):
            issue('related', 'related values must be document IDs')
    clean = prose(body)
    if kind:
        prefix, directory, statuses, sections = SPECS[kind]
        if isinstance(doc_id, str) and not doc_id.startswith(prefix + '-'):
            issue('type', f'{kind} requires prefix {prefix}')
        if metadata.get('status') not in statuses:
            issue('status', f'{kind} status must be one of: {", ".join(statuses)}')
        if workspace and path.parent.absolute() != (workspace.data / directory).absolute():
            issue('location', f'{kind} documents belong in .agence/{directory}')
        headings = re.findall(r'^##[ \t]+(.+?)[ \t]*$', clean, re.M)
        for section in sections:
            if section not in headings:
                issue('section', f'missing section: {section}')
        if kind == 'work':
            owner = metadata.get('owner')
            if not isinstance(owner, str) or not owner.strip():
                issue('owner', 'work requires a nonempty owner')
            elif workspace and owner not in workspace.roles:
                issue('owner', f'no installed role: {owner}')
    activity = []
    activity_match = re.search(r'^## Activity\s*\n(.*?)(?=^## |\Z)', clean, re.M | re.S)
    if activity_match:
        entries = list(re.finditer(r'^### (.+)$', activity_match[1], re.M))
        for i, entry in enumerate(entries):
            stop = entries[i+1].start() if i+1 < len(entries) else len(activity_match[1])
            activity.append((entry[1], activity_match[1][entry.end():stop].strip()))
    return Document(path, metadata, body, kind, activity), diagnostics


@dataclass
class Catalog:
    documents: list
    diagnostics: list

    def resolve(self, doc_id):
        return [d for d in self.documents if d.id == doc_id]


def catalog(workspace):
    documents, diagnostics = [], []
    # Include misplaced Markdown so location and unexpected files are visible.
    paths = []
    def traversal_error(error):
        diagnostics.append(Diagnostic(Path(error.filename), 'read', str(error)))
    linked_directories = {path for path in [workspace.data, *(workspace.data / name for name in DIRECTORIES)]
                          if path.is_symlink()}
    diagnostics.extend(Diagnostic(path, 'symlink',
        'symlinked coordination directory cannot be cataloged safely') for path in sorted(linked_directories))
    if workspace.data in linked_directories:
        return Catalog([], diagnostics)
    for directory, directories, names in os.walk(workspace.data, onerror=traversal_error):
        for name in list(directories):
            path = Path(directory) / name
            if path.is_symlink():
                if path not in linked_directories:
                    diagnostics.append(Diagnostic(path, 'symlink',
                        'symlinked coordination directory cannot be cataloged safely'))
                directories.remove(name)
        paths.extend(Path(directory) / name for name in names if name.endswith('.md'))
    for path in sorted(paths):
        relative = path.relative_to(workspace.data)
        if relative.parts[0] == 'roles' or relative == Path('INDEX.md'):
            continue
        document, issues = parse(path, workspace)
        diagnostics.extend(issues)
        if document:
            documents.append(document)
    ids = {}
    for document in documents:
        if isinstance(document.id, str):
            ids.setdefault(document.id, []).append(document)
    for doc_id, matches in ids.items():
        if len(matches) > 1:
            diagnostics.extend(Diagnostic(d.path, 'duplicate-id', f'duplicate workspace ID: {doc_id}') for d in matches)
    return Catalog(documents, diagnostics)


def slug(title):
    ascii_title = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', ascii_title.lower()).strip('-')
