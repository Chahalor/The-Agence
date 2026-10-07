"""Deterministic generated index and plain-text live status."""
from textwrap import fill
from urllib.parse import quote

VISIBLE = {'work': {'planned', 'active', 'blocked', 'review'},
           'decision': {'proposed', 'accepted'}, 'note': {'draft', 'current'},
           'report': {'draft', 'final'}}


def ordered(documents):
    return sorted(documents, key=lambda d: ('TDNR'.index(d.id[0]), int(d.id[2:])))


def escape(value):
    value = ' '.join(str(value).splitlines())
    for char in ('\\', '|', '[', ']', '*', '_', '`', '<', '>'):
        value = value.replace(char, '\\' + char)
    return value


def render_index(workspace, documents):
    documents = ordered(documents)
    lines = ['# The Agence Index', '',
             'Generated from source documents. Regenerate with `ta index`; do not edit manually.',
             '', '## Active work', '']
    work = [d for d in documents if d.kind == 'work' and d.metadata['status'] in VISIBLE['work']]
    if work:
        lines.extend(['| ID | Work | Status | Owner |', '|---|---|---|---|'])
        for d in work:
            link = quote(d.path.relative_to(workspace.data).as_posix())
            lines.append(f"| {d.id} | [{escape(d.metadata['title'])}]({link}) | {d.metadata['status']} | {escape(d.metadata['owner'])} |")
    else:
        lines.append('None.')
    for kind, heading in (('decision', 'Decisions'), ('note', 'Notes'), ('report', 'Reports')):
        lines.extend(['', f'## {heading}', ''])
        selected = [d for d in documents if d.kind == kind and d.metadata['status'] in VISIBLE[kind]]
        for d in selected:
            link = quote(d.path.relative_to(workspace.data).as_posix())
            lines.append(f"- [{d.id} — {escape(d.metadata['title'])}]({link}) — {d.metadata['status']}")
        if not selected:
            lines.append('None.')
    return '\n'.join(lines) + '\n'


def render_status(workspace, documents, selected=None):
    if selected:
        m = selected.metadata
        lines = [fill(f"{selected.id} — {m['title']}", width=88), '', f"status: {m['status']}"]
        if selected.kind == 'work':
            lines.append(f"owner: {m['owner']}")
        lines.extend(['', 'related:'])
        lines.extend('  ' + value for value in m['related'])
        if not m['related']:
            lines.append('  None.')
        lines.extend(['', 'last activity:'])
        if selected.activity:
            heading, body = selected.activity[-1]
            lines.append('  ' + heading)
            for line in body.splitlines():
                lines.append(fill(line, width=88, initial_indent='  ', subsequent_indent='  '))
        else:
            lines.append('  No activity.')
        return '\n'.join(lines) + '\n'
    lines = [workspace.root.name, '', 'Work', '─' * 64]
    work = [d for d in ordered(documents) if d.kind == 'work' and d.metadata['status'] in VISIBLE['work']]
    for d in work:
        prefix = f"{d.id:<8} {d.metadata['status']:<10} {d.metadata['owner']:<12} "
        lines.append(fill(' '.join(d.metadata['title'].split()), width=88,
                          initial_indent=prefix, subsequent_indent=' ' * len(prefix)))
    if not work:
        lines.append('No active work.')
    lines.extend(['', 'Knowledge', '─' * 64])
    for kind, heading in (('decision', 'Decisions'), ('note', 'Notes'), ('report', 'Reports')):
        lines.append(f'{heading:<10} {sum(d.kind == kind for d in documents)}')
    return '\n'.join(lines) + '\n'
