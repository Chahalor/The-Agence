"""argparse command tree and user-facing error handling."""
import argparse
import sys

from . import commands
from .documents import SPECS
from .workspace import AgenceError


def parser():
    root = argparse.ArgumentParser(prog='ta', description='The Agence Markdown/YAML workspace helpers')
    root.add_argument('--root', metavar='PATH', help='explicit workspace directory or its .agence directory')
    sub = root.add_subparsers(dest='command', required=True)
    setup = sub.add_parser('setup', help='initialize a workspace, preserving existing content')
    setup.add_argument('path', nargs='?', metavar='PATH')
    check = sub.add_parser('check', help='validate documents, layout and local references')
    checks = check.add_subparsers(dest='check_kind', required=True)
    for name in ('file', 'dir', 'refs', 'all'):
        p = checks.add_parser(name, help=f'check {name}')
        p.add_argument('path', nargs=None if name == 'file' else '?', metavar='FILE_OR_PATH' if name == 'file' else 'PATH',
                       help='target workspace directory or .agence directory' +
                            (' (or a single document file)' if name in ('file', 'refs') else ''))
    new = sub.add_parser('new', help='create a document and refresh the index')
    types = new.add_subparsers(dest='document_kind', required=True)
    for kind in SPECS:
        p = types.add_parser(kind, help=f'create a {kind}')
        p.add_argument('title', metavar='TITLE')
        if kind == 'work':
            p.add_argument('--owner', default='coder', metavar='ROLE')
        p.add_argument('--status', choices=SPECS[kind][2])
        p.add_argument('--tag', action='append', default=[])
        p.add_argument('--related', action='append', default=[], metavar='ID')
    sub.add_parser('index', help='regenerate the derived INDEX.md')
    status = sub.add_parser('status', help='show live workspace state or one document')
    status.add_argument('selection', nargs='?', metavar='ID_OR_FILE')
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command == 'setup' and args.path and args.root:
        from .workspace import explicit_workspace
        if explicit_workspace(args.path).root.resolve() != explicit_workspace(args.root).root.resolve():
            parser().error('setup PATH and --root must select the same target')
    try:
        output = getattr(commands, args.command)(args)
        sys.stdout.write(output)
        return 0
    except (AgenceError, OSError, UnicodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('Interrupted; any created documents are retained. Retry or run ta index.', file=sys.stderr)
        return 1
