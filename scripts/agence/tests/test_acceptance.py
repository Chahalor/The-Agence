"""Independent T-002 acceptance coverage beyond the coder's regression suite.

Set TA_TEST_INSTALLED=1 and run with the wheel environment's Python to exercise
installed modules outside the repository, with no source PYTHONPATH injection.
"""
from pathlib import Path
import os
import signal
import subprocess
import sys
import unittest

import yaml

from test_cli import Harness


class AcceptanceTests(Harness):
    def setUp(self):
        super().setUp()
        if os.environ.get('TA_TEST_INSTALLED') == '1':
            import agence
            self.env.pop('PYTHONPATH', None)
            self.assertIn('site-packages', Path(agence.__file__).parts,
                          'installed acceptance mode must import the built wheel')

    def tree_snapshot(self):
        """Detect new directories/locks as well as changed files on read paths."""
        return {p.relative_to(self.root):
                (p.is_dir(), p.stat().st_mode, p.stat().st_mtime_ns,
                 p.read_bytes() if p.is_file() else None)
                for p in self.root.rglob('*')}

    def test_all_lifecycle_statuses_and_empty_state(self):
        workspace = self.setup_workspace()
        empty = self.cli('--root', self.root, 'status').stdout
        self.assertIn('No active work.', empty)
        for label in ('Decisions', 'Notes', 'Reports'):
            self.assertRegex(empty, rf'{label}\s+0\b')
        # Expectations come from T-002, independently of implementation constants.
        cases = {
            'work': ('T', ('planned', 'active', 'blocked', 'review'),
                     ('completed', 'cancelled')),
            'decision': ('D', ('proposed', 'accepted'),
                         ('rejected', 'deprecated', 'superseded')),
            'note': ('N', ('draft', 'current'), ('outdated', 'superseded')),
            'report': ('R', ('draft', 'final'), ('obsolete',)),
        }
        expected = []
        for kind, (prefix, visible, historical) in cases.items():
            for number, status in enumerate((*visible, *historical), 1):
                with self.subTest(kind=kind, status=status):
                    path = self.create(kind, f'{kind} {status}', '--status', status)
                    metadata = yaml.safe_load(path.read_text().split('---', 2)[1])
                    identifier = f'{prefix}-{number:03d}'
                    self.assertEqual(metadata['id'], identifier)
                    self.assertEqual(metadata['status'], status)
                    self.assertEqual(metadata['schema'], f'agence/{kind}/v1')
                    detail = self.cli('--root', self.root, 'status', identifier).stdout
                    self.assertIn(f'status: {status}', detail)
                    expected.append((identifier, kind, status in visible, path))
        self.cli('check', 'all', self.root)
        index = (workspace.data / 'INDEX.md').read_text()
        overview = self.cli('--root', self.root, 'status').stdout
        for identifier, kind, visible, path in expected:
            with self.subTest(identifier=identifier):
                self.assertEqual(identifier in index, visible)
                self.assertTrue(path.is_file())
                if kind == 'work':
                    self.assertEqual(identifier in overview, visible)
                if visible:
                    self.assertIn(f']({path.relative_to(workspace.data).as_posix()})', index)
        for label, count in (('Decisions', 5), ('Notes', 4), ('Reports', 3)):
            self.assertRegex(overview, rf'{label}\s+{count}\b')

    def test_setup_defaults_to_cwd_even_with_ancestor_workspace(self):
        self.setup_workspace()
        self.create('work', 'Ancestor task')
        before = self.snapshot()
        child = self.root / 'nested project'
        child.mkdir()
        self.cli('setup', cwd=child)
        self.cli('--root', '.', 'setup', '.agence', cwd=child)
        self.cli('check', 'all', '.', cwd=child)
        self.assertIn('No active work.', self.cli('status', cwd=child).stdout)
        after = self.snapshot()
        self.assertEqual(before, {p: after[p] for p in before})
        self.assertTrue((child / '.agence' / 'INDEX.md').is_file())

    def test_custom_owner_repeatable_options_and_reference_cycles(self):
        workspace = self.setup_workspace()
        (workspace.data / 'roles' / 'release.md').write_text('# Custom role\n')
        work = self.create('work', 'Custom ownership', '--owner', 'release',
                           '--tag', 'a: b', '--tag', '[literal]')
        self.create('decision', 'Contract')
        note = self.create('note', 'Connections', '--related', 'T-001',
                           '--related', 'D-001')
        work.write_text(work.read_text().replace('related: []', 'related: [N-001, T-001]'))
        # Work -> note -> work and work -> itself are both valid.
        self.cli('check', 'all', self.root)
        self.cli('--root', self.root, 'index')
        detail = self.cli('--root', self.root, 'status', 'T-001').stdout
        self.assertIn('owner: release', detail)
        metadata = yaml.safe_load(work.read_text().split('---', 2)[1])
        self.assertEqual(metadata['tags'], ['a: b', '[literal]'])
        detail = self.cli('--root', self.root, 'status', note).stdout
        self.assertIn('  T-001\n  D-001\n', detail)

    def test_duplicate_ids_fail_selection_refs_and_mutations_without_writes(self):
        workspace = self.setup_workspace()
        original = self.create('work', 'Duplicate source')
        duplicate = original.with_name('T-001-other-name.md')
        duplicate.write_bytes(original.read_bytes())
        before = self.tree_snapshot()
        for selection in ('T-001', original):
            result = self.cli('--root', self.root, 'status', selection, code=1)
            self.assertIn('duplicate-id', result.stderr)
            self.assertEqual(result.stdout, '')
        result = self.cli('check', 'refs', self.root, code=1)
        self.assertIn('duplicate-id', result.stderr)
        for arguments in (('index',), ('new', 'note', 'Refused')):
            self.cli('--root', self.root, *arguments, code=1)
        # Mutations may briefly create/remove a lock, changing root mtime only.
        self.assertEqual(before, self.tree_snapshot())
        duplicate.unlink()
        self.cli('check', 'all', self.root)

    def test_failed_read_commands_preserve_tree_and_accumulate_findings(self):
        workspace = self.setup_workspace()
        work = self.create()
        work.write_text(work.read_text().replace('status: planned', 'status: incorrect') +
                        '\nN-999\n[missing](missing.md)\n')
        (workspace.data / 'roles' / 'docs.md').unlink()
        before = self.tree_snapshot()
        errors = self.cli('check', 'all', self.root, code=1)
        self.assertEqual(errors.stdout, '')
        for code in ('layout', 'status', 'reference-id', 'reference-path'):
            self.assertIn(f': {code}:', errors.stderr)
        self.assertEqual(errors.stderr, self.cli('check', 'all', self.root, code=1).stderr)
        for kind in ('file', 'dir', 'refs'):
            self.cli('check', kind, self.root, code=1)
        self.cli('--root', self.root, 'status', code=1)
        self.cli('--root', self.root, 'status', 'T-001', code=1)
        self.assertEqual(before, self.tree_snapshot())
        self.assertFalse((self.root / '.agence.lock').exists())

    def test_catalog_ignores_non_markdown_but_rejects_unexpected_markdown(self):
        workspace = self.setup_workspace()
        self.create()
        for filename in ('.gitkeep', 'helper.py', 'fixture.json'):
            (workspace.data / 'work' / filename).write_text('not an Agence document')
        self.cli('check', 'all', self.root)
        before = (workspace.data / 'INDEX.md').read_bytes()
        unexpected = workspace.data / 'work' / 'README.md'
        unexpected.write_text('# Unexpected document\n')
        self.assertIn('frontmatter', self.cli('check', 'all', self.root, code=1).stderr)
        self.cli('--root', self.root, 'index', code=1)
        self.assertEqual(before, (workspace.data / 'INDEX.md').read_bytes())

    def test_filename_matching_and_sections_outside_fences(self):
        self.setup_workspace()
        path = self.create()
        original = path.read_text()
        for filename in ('T-01-short.md', 'T-001-Upper.md', 'T-001-two--dashes.md',
                         'T-002-mismatched.md', 'N-001-wrong-type.md'):
            with self.subTest(filename=filename):
                invalid = path.with_name(filename)
                invalid.write_text(original)
                result = self.cli('check', 'file', invalid, code=1)
                self.assertRegex(result.stderr, r': (filename|id):')
                invalid.unlink()
        path.write_text(original.replace('## Goal', '```md\n## Goal\n```'))
        self.assertIn('missing section: Goal', self.cli('check', 'file', path, code=1).stderr)
        path.write_text(original.replace('tags: []',
            'extra: {created: 2026-10-07, enabled: true, nested: [1, 2]}\ntags: []'))
        self.cli('check', 'all', self.root)

    def test_reference_boundaries_parentheses_decoding_and_binary_targets(self):
        self.setup_workspace()
        note = self.create('note', 'References')
        source = self.root / 'folder (one)' / 'source.md'
        source.parent.mkdir()
        source.write_text('# Café\n\n## Duplicate\n\n## Duplicate\n')
        binary = self.root / 'binary.dat'
        binary.write_bytes(b'\xff\x00')
        with note.open('a') as stream:
            stream.write('\n[source](<../../../folder (one)/source.md#caf%C3%A9>)\n'
                         '[second](../../../folder%20%28one%29/source.md#duplicate-1)\n'
                         '[last line](<../../../folder (one)/source.md:5>)\n'
                         '[directory](<../../../folder (one)/>)\n'
                         '[binary](../../../binary.dat)\n')
        # A binary target is valid unless its contents must be read for a fragment/line.
        self.cli('check', 'refs', self.root)
        with note.open('a') as stream:
            stream.write('\n[negative line](<../../../folder (one)/source.md:-1>)\n'
                         '[past end](<../../../folder (one)/source.md:6>)\n'
                         '[directory fragment](<../../../folder (one)/#absent>)\n'
                         '[binary fragment](../../../binary.dat#absent)\n')
        errors = self.cli('check', 'refs', self.root, code=1).stderr
        for rule in ('reference-line', 'reference-path', 'reference-read'):
            self.assertIn(f': {rule}:', errors)

    @unittest.skipIf(os.name != 'posix' or getattr(os, 'geteuid', lambda: 0)() == 0,
                     'requires POSIX permissions enforced for a non-root user')
    def test_permission_failure_during_setup_is_partial_and_retryable(self):
        roles = self.root / '.agence' / 'roles'
        roles.mkdir(parents=True)
        roles.chmod(0o555)
        try:
            result = self.cli('setup', self.root, code=1)
            self.assertIn('Permission denied', result.stderr)
            self.assertIn('Setup incomplete. Created:', result.stderr)
            self.assertIn(str(self.root / 'AGENTS.md'), result.stderr)
            self.assertEqual(result.stdout, '')
            self.assertTrue((self.root / 'AGENTS.md').is_file())
            self.assertFalse((self.root / '.agence.lock').exists())
        finally:
            roles.chmod(0o755)
        (self.root / 'AGENTS.md').write_text('Preserve partial setup customization\n')
        self.cli('setup', self.root)
        self.assertEqual((self.root / 'AGENTS.md').read_text(),
                         'Preserve partial setup customization\n')
        self.cli('check', 'all', self.root)

    @unittest.skipIf(os.name != 'posix' or getattr(os, 'geteuid', lambda: 0)() == 0,
                     'requires POSIX permissions enforced for a non-root user')
    def test_permission_failure_before_creation_preserves_workspace(self):
        workspace = self.setup_workspace()
        directory = workspace.data / 'work'
        directory.chmod(0o555)
        try:
            before = self.tree_snapshot()
            result = self.cli('--root', self.root, 'new', 'work', 'Denied', code=1)
            self.assertIn('Permission denied', result.stderr)
            self.assertEqual(result.stdout, '')
            self.assertEqual(before, self.tree_snapshot())
            self.assertFalse((self.root / '.agence.lock').exists())
        finally:
            directory.chmod(0o755)
        self.assertEqual(self.create('work', 'Retry').name, 'T-001-retry.md')

    @unittest.skipIf(os.name != 'posix' or getattr(os, 'geteuid', lambda: 0)() == 0,
                     'requires POSIX permissions enforced for a non-root user')
    def test_real_index_failure_retains_created_document_and_recovers(self):
        workspace = self.setup_workspace()
        index = workspace.data / 'INDEX.md'
        before = index.read_bytes()
        workspace.data.chmod(0o555)
        try:
            result = self.cli('--root', self.root, 'new', 'work', 'Retained file', code=1)
            created = workspace.data / 'work' / 'T-001-retained-file.md'
            self.assertTrue(created.is_file())
            self.assertIn(str(created), result.stderr)
            self.assertIn('Document retained', result.stderr)
            self.assertIn('ta index', result.stderr)
            self.assertEqual(result.stdout, '')
            self.assertEqual(before, index.read_bytes())
            self.assertFalse((self.root / '.agence.lock').exists())
            self.assertEqual(list(workspace.data.glob('.INDEX-*')), [])
        finally:
            workspace.data.chmod(0o755)
        self.cli('--root', self.root, 'index')
        self.assertIn('T-001', index.read_text())
        self.cli('check', 'all', self.root)
        self.assertEqual(self.create('work', 'After recovery').name, 'T-002-after-recovery.md')

    @unittest.skipUnless(hasattr(signal, 'SIGINT'), 'requires SIGINT')
    def test_sigint_at_publication_reports_failure_and_retains_document(self):
        workspace = self.setup_workspace()
        index = workspace.data / 'INDEX.md'
        before = index.read_bytes()
        # Send a real signal at a controlled I/O boundary: no timing race or sleep.
        script = '''
import os, signal, sys
from unittest.mock import patch
from agence.cli import main
from agence.workspace import Workspace
def interrupt(*args):
    os.kill(os.getpid(), signal.SIGINT)
with patch.object(Workspace, 'publish_index', side_effect=interrupt):
    sys.exit(main(sys.argv[1:]))
'''
        result = subprocess.run([sys.executable, '-c', script, '--root', str(self.root),
                                 'new', 'work', 'Signal interrupted'],
                                cwd=self.temporary.name, env=self.env,
                                text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertIn('Document retained', result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertTrue((workspace.data / 'work' / 'T-001-signal-interrupted.md').is_file())
        self.assertEqual(before, index.read_bytes())
        self.assertFalse((self.root / '.agence.lock').exists())
        self.cli('--root', self.root, 'index')
        self.cli('check', 'all', self.root)


if __name__ == '__main__':
    unittest.main()
