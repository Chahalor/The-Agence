"""Read-only layout and local reference validation; never fetch external links."""
from pathlib import Path
import os
import re
from urllib.parse import unquote, urlsplit

from .documents import Diagnostic, prose
from .workspace import DIRECTORIES, ROLES

SOURCE_SUFFIX = re.compile(r'\.(?:md|py|c|h|cpp|hpp|rs|js|ts|tsx|json|ya?ml|toml|txt|sh)(?::-?\d+)?$')


def check_directory(workspace):
    diagnostics = []
    required = [(workspace.root / 'AGENTS.md', False), (workspace.data, True),
                (workspace.data / 'INDEX.md', False)]
    required += [(workspace.data / p, True) for p in DIRECTORIES]
    required += [(workspace.data / 'roles' / f'{role}.md', False) for role in ROLES]
    for path, directory in required:
        if directory and path.is_symlink():
            diagnostics.append(Diagnostic(path, 'symlink', 'symlinked coordination directory is unsupported'))
        elif not (path.is_dir() if directory else path.is_file()):
            diagnostics.append(Diagnostic(path, 'layout', f'missing or incompatible {"directory" if directory else "file"}'))
    return diagnostics


def heading_anchors(text):
    anchors, counts = set(), {}
    for heading in re.findall(r'^#{1,6}\s+(.+?)(?:\s+#+)?\s*$', prose(text), re.M):
        heading = re.sub(r'<[^>]+>', '', heading)
        base = re.sub(r'[^\w\s-]', '', heading.lower())
        base = re.sub(r'\s', '-', base)
        number = counts.get(base, 0)
        candidate = base if not number else f'{base}-{number}'
        while candidate in anchors:
            number += 1
            candidate = f'{base}-{number}'
        counts[base] = number + 1
        anchors.add(candidate)
    return anchors


def check_references(document, workspace, catalog):
    diagnostics = []
    clean = prose(document.body)

    def issue(code, message, position=None):
        diagnostics.append(Diagnostic(document.path, code, message))

    def identifier(value):
        matches = catalog.resolve(value)
        if len(matches) != 1:
            issue('reference-id', f'{value}: {"missing" if not matches else "ambiguous"} document ID')

    related = document.metadata.get('related')
    if isinstance(related, list):
        for value in related:
            if isinstance(value, str):
                identifier(value)

    def target(value, link=False):
        value = value.strip()
        bare_line = re.fullmatch(r'[^/:]+:-?\d+', value) is not None and SOURCE_SUFFIX.search(value) is not None
        if re.match(r'^[a-zA-Z][\w+.-]*:', value) and not bare_line:
            return  # URL schemes, including mailto, are external.
        if value.startswith('//'):
            return
        if any(c in value for c in ('<', '>', '\\', '\n')):
            issue('reference-syntax', f'unsupported local target: {value}')
            return
        try:
            # A bare filename followed by :line otherwise looks like a URI
            # scheme to urlsplit (for example source.py:42).
            parsed = urlsplit('./' + value if bare_line else value)
        except ValueError:
            issue('reference-syntax', f'unsupported local target: {value}')
            return
        if parsed.query:
            issue('reference-syntax', f'local query strings are unsupported: {value}')
            return
        path_text = unquote(parsed.path)
        fragment = unquote(parsed.fragment)
        line = None
        match = re.search(r':(-?\d+)$', path_text)
        if match:
            line = int(match[1])
            path_text = path_text[:match.start()]
        path = (document.path.parent if link else workspace.source_root) / path_text if path_text else document.path
        if not path.exists():
            issue('reference-path', f'missing target: {value} (resolved to {os.path.relpath(path, workspace.data)})')
            return
        if line is not None or fragment:
            if not path.is_file():
                issue('reference-path', f'line/fragment requires a file: {value}')
                return
            try:
                text = path.read_text(encoding='utf-8')
            except (OSError, UnicodeError) as exc:
                issue('reference-read', f'{value}: {exc}')
                return
            if line is not None and (line < 1 or line > len(text.splitlines())):
                issue('reference-line', f'line out of range: {value}')
            if fragment and fragment not in heading_anchors(text):
                issue('reference-anchor', f'missing heading anchor: {value}')

    # Inline code is only a source reference when it looks like a path; generic
    # expressions and command arguments are excluded. Bare IDs in code are examples.
    code = re.compile(r'(`+)(.*?)\1', re.S)
    path_suffix = SOURCE_SUFFIX
    for match in code.finditer(clean):
        value = match[2].strip()
        if ('/' in value or path_suffix.search(value)) and not re.search(r'[<>{}*()=]|^--', value) and (not re.search(r'\s', value) or path_suffix.search(value) or value.endswith('/')):
            target(value)
    remaining = code.sub(lambda m: ' ' * len(m[0]), clean)
    # Consume escape pairs left to right. Escaped Markdown delimiters are
    # literal text; a doubled backslash still leaves the next delimiter active.
    remaining = re.sub(r'\\[\\\[\]()!]', lambda m: ' ' * len(m[0]), remaining)

    # Definitions support angle-bracket destinations (including spaces), or a
    # non-whitespace destination with an optional quoted title.
    definitions = {}
    definition_pattern = re.compile(r'^ {0,3}\[([^\]]+)\]:\s*(.*)$', re.M)
    for match in definition_pattern.finditer(remaining):
        definitions[match[1].strip().casefold()] = match[2]

    def destination(raw):
        raw = raw.strip()
        if raw.startswith('<'):
            found = re.fullmatch(r'<([^>]+)>(?:\s+[\'"].*[\'"])?', raw)
        else:
            found = re.fullmatch(r'(\S+?)(?:\s+[\'"].*[\'"])?', raw)
        if not found:
            issue('reference-syntax', f'unsupported link destination: {raw}')
        else:
            target(found[1], link=True)

    for raw in definitions.values():
        destination(raw)
    remaining = definition_pattern.sub(lambda m: ' ' * len(m[0]), remaining)
    inline = re.compile(r'!?\[([^\]\n]*)\]\((<[^>]*>|[^\n]*?)\)')
    for match in inline.finditer(remaining):
        raw = match[2]
        if not raw.startswith('<') and ('(' in raw or (match.end() < len(remaining) and remaining[match.end()] == ')')):
            issue('reference-syntax', f'parenthesized link targets require angle brackets: {raw}')
        else:
            destination(raw)
    remaining = inline.sub(lambda m: ' ' * len(m[0]), remaining)
    if re.search(r'!?\[[^\]\n]*\]\(', remaining):
        issue('reference-syntax', 'unterminated or unsupported inline link')
    reference = re.compile(r'!?\[([^\]\n]+)\]\[([^\]\n]*)\]')
    for match in reference.finditer(remaining):
        label = (match[2] or match[1]).strip().casefold()
        if label not in definitions:
            issue('reference-link', f'undefined link label: {label}')
    remaining = reference.sub(lambda m: ' ' * len(m[0]), remaining)
    # Shortcut links are links only when a corresponding definition exists.
    shortcut = re.compile(r'!?\[([^\]\n]+)\]')
    remaining = shortcut.sub(lambda m: ' ' * len(m[0]) if m[1].strip().casefold() in definitions else m[0], remaining)
    # Mask filename/path tokens so T-001-title.md cannot also mean bare T-001.
    remaining = re.sub(r'\S*(?:/|\.md)\S*', '', remaining)
    for value in sorted(set(re.findall(r'(?<![\w-])[TDNR]-[0-9]{3,}(?![\w-])', remaining))):
        identifier(value)
    return diagnostics
