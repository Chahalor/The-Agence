"""Local acceptance tests; separate tester/reviewer validation is still required."""
from argparse import Namespace
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from agence import commands
from agence.checks import check_references
from agence.documents import catalog, parse
from agence.workspace import AgenceError, Workspace


class Harness(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='agence tests ')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'project with spaces'
        self.env = os.environ.copy()
        self.env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1] / 'src')

    def cli(self, *arguments, code=0, cwd=None):
        result = subprocess.run([sys.executable, '-m', 'agence', *map(str, arguments)],
                                cwd=cwd or self.temporary.name, env=self.env,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        return result

    def setup_workspace(self):
        self.cli('setup', self.root)
        return Workspace(self.root)

    def create(self, kind='work', title='Example title', *options):
        result = self.cli('--root', self.root, 'new', kind, title, *options)
        return Path(result.stdout.strip())

    def snapshot(self):
        return {p.relative_to(self.root): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.root.rglob('*') if p.is_file()}


class CliTests(Harness):
    def test_every_check_accepts_directory_targets(self):
        workspace = self.setup_workspace()
        self.create()
        before = self.snapshot()
        for kind in ('file', 'dir', 'refs', 'all'):
            for target in (self.root.name, f'{self.root.name}/.agence'):
                with self.subTest(kind=kind, target=target):
                    self.cli('check', kind, target)
        self.assertEqual(before, self.snapshot())
        # An explicit target wins over --root, including for check file.
        other = Path(self.temporary.name)/'other'
        self.cli('setup', other)
        self.cli('--root', other, 'check', 'file', self.root)

    def test_check_diagnostics_relative_to_agence(self):
        workspace = self.setup_workspace()
        task = self.create()
        task.write_text(task.read_text().replace('status: planned', 'status: wrong') +
                        '\n`missing/source.py`\n')
        for kind in ('file', 'all'):
            result = self.cli('check', kind, self.root, code=1)
            self.assertIn('work/T-001-example-title.md: status:', result.stderr)
            self.assertNotIn(str(self.root), result.stderr)
        result = self.cli('check', 'file', task, code=1)
        self.assertTrue(result.stderr.startswith('work/T-001-example-title.md:'))
        result = self.cli('check', 'refs', self.root, code=1)
        self.assertIn('resolved to ../missing/source.py', result.stderr)
        self.assertNotIn(str(self.root), result.stderr)
        (self.root/'AGENTS.md').unlink()
        result = self.cli('check', 'dir', workspace.data, code=1)
        self.assertIn('../AGENTS.md: layout:', result.stderr)
        self.assertNotIn(str(self.root), result.stderr)

    def test_standalone_check_error_relative_to_cwd(self):
        path = Path(self.temporary.name)/'T-001-standalone.md'
        path.write_text('invalid')
        result = self.cli('check', 'file', path, code=1)
        self.assertTrue(result.stderr.startswith('T-001-standalone.md:'))
        self.assertNotIn(self.temporary.name, result.stderr)

    def test_help_every_command(self):
        for args in ((), ('setup',), ('check',), ('new',), ('index',), ('status',),
                     *(('check', k) for k in ('file','dir','refs','all')),
                     *(('new', k) for k in ('work','decision','note','report'))):
            self.assertIn('usage:', self.cli(*args, '--help').stdout)
        self.cli('check', code=2)
        self.cli('--root', self.root, 'setup', Path(self.temporary.name)/'different', code=2)

    def test_end_to_end_all_types(self):
        self.setup_workspace()
        work = self.create('work', 'Écrire: "YAML" | safe', '--tag', 'a:b', '--tag', 'two', '--status', 'active')
        self.create('decision', 'Choose format', '--related', 'T-001', '--status', 'accepted')
        self.create('note', 'Useful facts', '--related', 'D-001')
        self.create('report', 'Measurements', '--status', 'final')
        self.cli('--root', self.root, 'check', 'all')
        self.cli('check', 'dir', self.root / '.agence')
        self.cli('check', 'all', self.root)
        self.cli('--root', self.root, 'check', 'file', work)
        self.cli('--root', self.root, 'check', 'refs', work)
        self.cli('--root', self.root / '.agence', 'index')
        overview = self.cli('--root', self.root, 'status').stdout
        for value in ('T-001', 'active', 'coder', 'Decisions', 'Notes', 'Reports'):
            self.assertIn(value, overview)
        detail = self.cli('--root', self.root, 'status', 'D-001').stdout
        self.assertIn('T-001', detail)
        self.assertIn('No activity.', detail)
        self.assertIn('Écrire', self.cli('--root', self.root, 'status', work).stdout)
        parsed, diagnostics = parse(work, Workspace(self.root))
        self.assertFalse(diagnostics)
        self.assertEqual(parsed.metadata['tags'], ['a:b', 'two'])

    def test_discovery_nearest_and_relative_paths(self):
        self.setup_workspace()
        nested = self.root / 'nested'
        nested.mkdir()
        self.cli('setup', '.', cwd=nested)
        self.cli('new', 'work', 'Inner task', cwd=nested)
        self.assertIn('T-001', self.cli('status', cwd=nested).stdout)
        self.assertNotIn('T-001', self.cli('--root', '..', 'status', cwd=nested).stdout)
        self.cli('check', 'dir', '..', cwd=nested)
        self.cli('status', code=1)
        other = Path(self.temporary.name) / 'empty'
        other.mkdir()
        self.cli('check', 'dir', other, code=1)
        self.assertEqual(list(other.iterdir()), [])

    def test_setup_preserves_custom_content_and_history(self):
        workspace = self.setup_workspace()
        rules = self.root / 'AGENTS.md'
        role = workspace.data / 'roles' / 'coder.md'
        rules.write_text('Customized rules\n')
        role.write_text('Customized coder\n')
        task = self.create()
        original = task.read_bytes()
        self.assertIn('Existing AGENTS.md preserved', self.cli('setup', self.root).stdout)
        self.assertEqual(rules.read_text(), 'Customized rules\n')
        self.assertEqual(role.read_text(), 'Customized coder\n')
        self.assertEqual(task.read_bytes(), original)
        (workspace.data / 'roles' / 'docs.md').unlink()
        self.cli('setup', self.root)
        self.assertTrue((workspace.data / 'roles' / 'docs.md').is_file())

    def test_setup_preflight_no_partial_writes(self):
        self.root.mkdir()
        (self.root / '.agence').write_text('collision')
        self.cli('setup', self.root, code=1)
        self.assertFalse((self.root / 'AGENTS.md').exists())
        self.assertFalse((self.root / '.agence.lock').exists())

    def test_setup_invalid_catalog_preserves_index(self):
        workspace = self.setup_workspace()
        index = workspace.data / 'INDEX.md'
        original = index.read_bytes()
        (workspace.data / 'work' / 'bad.md').write_text('invalid')
        result = self.cli('setup', self.root, code=1)
        self.assertIn('Setup incomplete', result.stderr)
        self.assertEqual(index.read_bytes(), original)
        self.assertFalse((self.root / '.agence.lock').exists())

    def test_read_only_commands_and_live_status(self):
        workspace = self.setup_workspace()
        task = self.create()
        (workspace.data / 'INDEX.md').write_text('stale index')
        before = self.snapshot()
        self.cli('--root', self.root, 'check', 'all')
        self.cli('--root', self.root, 'status')
        self.cli('--root', self.root, 'status', task)
        self.assertEqual(before, self.snapshot())
        self.assertFalse((self.root / '.agence.lock').exists())

    def test_deterministic_index_and_terminal_filter(self):
        workspace = self.setup_workspace()
        self.create('work', 'Closed', '--status', 'completed')
        self.create('work', 'Visible | [task]\nsecond line')
        self.create('decision', 'Old', '--status', 'deprecated')
        self.create('note', 'Old', '--status', 'outdated')
        self.create('report', 'Old', '--status', 'obsolete')
        index = workspace.data / 'INDEX.md'
        original = index.read_bytes()
        self.cli('--root', self.root, 'index')
        self.assertEqual(original, index.read_bytes())
        self.assertNotIn('T-001', index.read_text())
        self.assertIn(r'Visible \| \[task\] second line', index.read_text())
        overview = self.cli('--root', self.root, 'status').stdout
        self.assertIn('Decisions  1', overview)
        self.assertNotIn('T-001', overview)
        index.unlink()
        self.cli('--root', self.root, 'index')
        self.assertEqual(original, index.read_bytes())

    def test_handoff_detail(self):
        self.setup_workspace()
        task = self.create()
        with task.open('a') as stream:
            stream.write('\n### result · coder\n\nFinished.\n\n### handoff · coder → tester\n\nValidate boundary cases.\n')
        detail = self.cli('--root', self.root, 'status', 'T-001').stdout
        self.assertIn('handoff · coder → tester', detail)
        self.assertIn('Validate boundary cases.', detail)
        self.assertNotIn('Finished.', detail)
        self.cli('--root', self.root, 'status', 'T-999', code=1)

    def test_creation_rejects_invalid_options_without_writes(self):
        self.setup_workspace()
        before = self.snapshot()
        for options in (('work','!!!'), ('work','Title','--owner','missing'),
                        ('note','Title','--related','N-999'), ('note','Title','--tag','')):
            self.cli('--root', self.root, 'new', *options, code=1)
            # Empty tags are rejected by schema before creation.
            self.assertEqual(before, self.snapshot())
        self.cli('--root', self.root, 'new', 'work', 'Title', '--status', 'final', code=2)

    def test_id_expansion_duplicate_and_malformed_allocation(self):
        workspace = self.setup_workspace()
        task = self.create()
        text = task.read_text().replace('T-001','T-999')
        task.unlink()
        old = workspace.data / 'work' / 'T-999-example-title.md'
        old.write_text(text)
        next_task = self.create('work', 'Next')
        self.assertTrue(next_task.name.startswith('T-1000-'))
        duplicate = workspace.data / 'work' / 'T-999-duplicate.md'
        duplicate.write_text(text)
        self.cli('--root', self.root, 'new', 'work', 'Refused', code=1)
        duplicate.unlink()
        old.write_text(text.replace('T-999','bogus'))
        self.cli('--root', self.root, 'new', 'work', 'Refused', code=1)

    def test_lock_held_cleanup_and_symlink_safety(self):
        workspace = self.setup_workspace()
        with workspace.lock():
            self.cli('--root', self.root, 'new', 'work', 'Locked', code=1)
            self.cli('setup', self.root, code=1)
            self.cli('--root', self.root, 'status')
        self.assertFalse((self.root / '.agence.lock').exists())
        outside = Path(self.temporary.name) / 'outside'
        outside.mkdir()
        (workspace.data / 'work').rmdir()
        (workspace.data / 'work').symlink_to(outside, target_is_directory=True)
        self.cli('--root', self.root, 'new', 'work', 'Escapes', code=1)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.root / '.agence.lock').exists())

    def test_publication_failure_retains_document_and_cleans_lock(self):
        workspace = self.setup_workspace()
        args = Namespace(root=str(self.root), document_kind='work', title='Retained',
                         status=None, owner='coder', tag=[], related=[])
        before = (workspace.data / 'INDEX.md').read_bytes()
        with patch.object(Workspace, 'publish_index', side_effect=OSError('disk failure')):
            with self.assertRaisesRegex(AgenceError, 'Document retained'):
                commands.new(args)
        self.assertTrue((workspace.data / 'work' / 'T-001-retained.md').exists())
        self.assertEqual((workspace.data / 'INDEX.md').read_bytes(), before)
        self.assertFalse((self.root / '.agence.lock').exists())
        self.cli('--root', self.root, 'index')

    def test_atomic_replace_failure_cleans_temporary(self):
        workspace = self.setup_workspace()
        original = (workspace.data / 'INDEX.md').read_bytes()
        with patch('agence.workspace.os.replace', side_effect=OSError('replace failed')):
            with self.assertRaises(OSError):
                workspace.publish_index('replacement')
        self.assertEqual((workspace.data / 'INDEX.md').read_bytes(), original)
        self.assertEqual(list(workspace.data.glob('.INDEX-*')), [])

    def test_interrupted_publication_retains_document(self):
        workspace = self.setup_workspace()
        args = Namespace(root=str(self.root), document_kind='work', title='Interrupted',
                         status=None, owner='coder', tag=[], related=[])
        with patch.object(Workspace, 'publish_index', side_effect=KeyboardInterrupt):
            with self.assertRaisesRegex(AgenceError, 'Created .*Interrupted|Document retained'):
                commands.new(args)
        self.assertTrue((workspace.data/'work'/'T-001-interrupted.md').exists())
        self.assertFalse((self.root/'.agence.lock').exists())

    def test_index_symlink_and_unreadable_catalog(self):
        workspace = self.setup_workspace()
        self.create()
        outside = Path(self.temporary.name)/'outside-index.md'
        outside.write_text('preserve outside')
        (workspace.data/'INDEX.md').unlink()
        (workspace.data/'INDEX.md').symlink_to(outside)
        self.cli('--root', self.root, 'index', code=1)
        self.assertEqual(outside.read_text(), 'preserve outside')
        with patch('agence.documents.os.walk') as walk:
            def failed_walk(*args, **kwargs):
                kwargs['onerror'](PermissionError(13, 'Permission denied', str(workspace.data/'work')))
                return iter(())
            walk.side_effect = failed_walk
            self.assertTrue(catalog(workspace).diagnostics)

    def test_missing_reference_target_is_failure(self):
        self.setup_workspace()
        self.cli('--root', self.root, 'check', 'refs', self.root/'missing.md', code=1)
        self.cli('check', 'refs', Path(self.temporary.name)/'absent', code=1)

    def test_packaged_roles_match_canonical_templates(self):
        from agence.workspace import template
        repository = Path(__file__).resolve().parents[3]
        for role in ('architect','coder','tester','reviewer','perfs','docs'):
            self.assertEqual(template(f'roles/{role}.md'),
                             (repository/'Workspaces'/f'{role}.md').read_text())
        global_template = template('AGENTS.md')
        self.assertTrue(global_template.startswith((repository/'Workspaces'/'AGENTS.md').read_text()))
        self.assertIn('Generated index ownership', global_template)
        self.assertNotIn('Scripts workspace context', global_template)

    def test_symlinked_catalog_directories_fail_without_publishing(self):
        workspace = self.setup_workspace()
        self.create('work', 'Preserved work')
        self.create('note', 'Preserved note')
        for name in ('work', 'knowledge/notes', 'knowledge', '.'):
            with self.subTest(directory=name):
                managed = workspace.data if name == '.' else workspace.data/name
                saved = self.root/('saved-' + name.replace('/', '-').replace('.', 'agence'))
                managed.rename(saved)
                managed.symlink_to(saved, target_is_directory=True)
                try:
                    before = self.snapshot()
                    self.assertIn('symlink', self.cli('check', 'all', self.root, code=1).stderr)
                    self.assertIn('symlink', self.cli('--root', self.root, 'status', code=1).stderr)
                    self.cli('--root', self.root, 'index', code=1)
                    self.cli('--root', self.root, 'new', 'note', 'Rejected', code=1)
                    self.assertEqual(before, self.snapshot())
                    self.assertFalse((self.root/'.agence.lock').exists())
                finally:
                    managed.unlink()
                    saved.rename(managed)
        self.cli('check', 'all', self.root)

    def test_broken_symlinked_document_directory_is_not_an_empty_catalog(self):
        workspace = self.setup_workspace()
        (workspace.data/'work').rmdir()
        (workspace.data/'work').symlink_to(self.root/'missing', target_is_directory=True)
        self.assertIn('symlink', self.cli('--root', self.root, 'status', code=1).stderr)

    def test_concurrent_id_allocation(self):
        self.setup_workspace()
        invocation = [sys.executable, '-m', 'agence', '--root', str(self.root), 'new', 'work']
        processes = [subprocess.Popen(invocation + [f'Task {i}'], env=self.env,
                        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for i in range(6)]
        created = []
        for process in processes:
            out, err = process.communicate(timeout=20)
            if process.returncode == 0:
                created.append(Path(out.strip()))
            else:
                self.assertIn('locked', err)
        self.assertTrue(created)
        ids = [p.name.split('-',2)[:2] for p in created]
        self.assertEqual(len(ids), len({tuple(value) for value in ids}))
        self.cli('--root', self.root, 'check', 'all')
        self.assertFalse((self.root / '.agence.lock').exists())


class ParsingTests(Harness):
    def test_invalid_yaml_dates_accumulate_diagnostics_without_traceback(self):
        workspace = self.setup_workspace()
        path = self.create()
        other = self.create('note', 'Other problem')
        other.write_text(other.read_text().replace('status: draft', 'status: invalid'))
        original = path.read_text()
        for timestamp in ('2026-13-01', '2026-02-30', '2026-10-07T25:00:00Z'):
            with self.subTest(timestamp=timestamp):
                path.write_text(original.replace('tags: []', 'created: ' + timestamp + '\ntags: []'))
                result = self.cli('check', 'all', self.root, code=1)
                self.assertIn('yaml:', result.stderr)
                self.assertIn('status:', result.stderr)
                self.cli('check', 'file', path, code=1)
                before = (workspace.data/'INDEX.md').read_bytes()
                self.cli('--root', self.root, 'status', code=1)
                self.cli('--root', self.root, 'index', code=1)
                self.cli('--root', self.root, 'new', 'note', 'Rejected', code=1)
                self.assertEqual(before, (workspace.data/'INDEX.md').read_bytes())
                self.assertFalse((self.root/'.agence.lock').exists())
        path.write_text(original.replace('tags: []', 'created: 2026-10-07\ntags: []'))
        self.cli('check', 'file', path)

    def test_escaped_markdown_titles_and_delimiters_are_literal(self):
        self.setup_workspace()
        note = self.create('note', 'Fix [API](v2)')
        self.cli('check', 'all', self.root)
        with note.open('a') as stream:
            stream.write(r'\[literal](missing)' + '\n' +
                         r'[literal]\(missing)' + '\n' +
                         r'\![literal]\(missing)' + '\n' +
                         r'\[literal][undefined]' + '\n' +
                         r'\[label]: missing.md' + '\n')
        self.cli('check', 'all', self.root)
        # An even number of backslashes leaves the bracket unescaped.
        with note.open('a') as stream:
            stream.write(r'\\[actual](missing.md)' + '\n')
        self.assertIn('reference-path', self.cli('check', 'all', self.root, code=1).stderr)

    def test_scheme_urls_with_numeric_suffix_never_read_local_targets(self):
        workspace = self.setup_workspace()
        note = self.create('note', 'External links')
        with note.open('a') as stream:
            for value in ('https://example.com/tickets/123:42',
                          'http://example.com:8080', 'mailto:42',
                          'custom.scheme:42', '//example.com/123:42'):
                stream.write(f'\n[external]({value})\n')
        document, errors = parse(note, workspace)
        self.assertFalse(errors)
        # Any local existence check here means a URL escaped scheme detection.
        with patch.object(Path, 'exists', side_effect=AssertionError('URL read as a local target')):
            self.assertEqual(check_references(document, workspace, catalog(workspace)), [])
        self.cli('check', 'all', self.root)
        source = self.root/'source.py'
        source.write_text('one\ntwo\n')
        with note.open('a') as stream:
            stream.write('\n`source.py:2`\n')
        self.cli('check', 'all', self.root)
        with note.open('a') as stream:
            stream.write('\n`source.py:99`\n')
        self.assertIn('reference-line', self.cli('check', 'all', self.root, code=1).stderr)

    def test_yaml_and_schema_failures(self):
        workspace = self.setup_workspace()
        path = self.create()
        original = path.read_text()
        cases = [('id: T-001','id: T-001\nid: T-002','yaml'),
                 ('tags: []','tags: scalar','tags'),
                 ('related: []','related: [plain]','related'),
                 ('title: Example title','title: 123','title'),
                 ('status: planned','status: final','status'),
                 ('owner: coder','owner: nobody','owner'),
                 ('schema: agence/work/v1','schema: agence/note/v1','type'),
                 ('## Goal','## Other','section')]
        for old, new, expected in cases:
            with self.subTest(expected=expected):
                path.write_text(original.replace(old,new))
                result = self.cli('--root', self.root, 'check', 'file', path, code=1)
                self.assertIn(expected, result.stderr)
        for text in ('plain','---\nid: T-001', '---\n- value\n---\n',
                     '---\nkey: !!python/object/apply:os.system [echo forbidden]\n---\n',
                     '---\ntitle: [\n---\n'):
            path.write_text(text)
            self.cli('check', 'file', path, code=1)
        path.write_text(original)
        standalone = Path(self.temporary.name) / path.name
        standalone.write_text(original)
        self.cli('check', 'file', standalone)
        misplaced = workspace.data / 'knowledge' / path.name
        misplaced.write_text(original)
        self.assertIn('location', self.cli('--root', self.root, 'check', 'all', code=1).stderr)

    def test_references_real_paths_spaces_fences_and_anchors(self):
        workspace = self.setup_workspace()
        path = self.create()
        source = self.root / 'folder with spaces' / 'source.md'
        source.parent.mkdir()
        source.write_text('# Hello, world!\n\n## Duplicate\n\n## Duplicate\n')
        with path.open('a') as stream:
            stream.write('\nT-001\n`folder with spaces/source.md:1`\n'
                         '[first](../../folder%20with%20spaces/source.md#hello-world)\n'
                         '[second](<../../folder with spaces/source.md#duplicate-1>)\n'
                         '![image][target]\n[target]: <../../folder with spaces/source.md> "Title"\n'
                         '[target]\n[self](#goal)\n[external](https://example.com/missing)\n'
                         '```md\nT-999\n`missing/file.py`\n[missing](does-not-exist)\n```\n'
                         '~~~\nD-999\n~~~\n`D-999`\n`function(a/b)`\n')
        self.cli('--root', self.root, 'check', 'all')
        with path.open('a') as stream:
            stream.write('\nN-999\n`missing/file.py`\n`folder with spaces/source.md:0`\n'
                         '[bad](../../folder%20with%20spaces/source.md#absent)\n'
                         '[bad][undefined]\n[bad](../../file?query)\n')
        result = self.cli('--root', self.root, 'check', 'all', code=1)
        for rule in ('reference-id','reference-path','reference-line','reference-anchor','reference-link','reference-syntax'):
            self.assertIn(rule, result.stderr)

    def test_reference_filename_not_bare_id_and_git_root(self):
        workspace = self.setup_workspace()
        (Path(self.temporary.name)/'.git').mkdir()
        (Path(self.temporary.name)/'.git'/'HEAD').write_text('ref: refs/heads/main\n')
        source = Path(self.temporary.name)/'source.py'
        source.write_text('one\ntwo\n')
        path = self.create()
        with path.open('a') as stream:
            stream.write('\n`source.py:2`\n[self](T-001-example-title.md)\n')
        self.cli('--root', self.root, 'check', 'refs')
        path.write_text(path.read_text()+'\n[bad](T-999-not-existing.md)\n')
        result = self.cli('--root', self.root, 'check', 'refs', code=1)
        self.assertIn('reference-path', result.stderr)
        self.assertNotIn('reference-id', result.stderr)

    def test_check_all_accumulates_and_is_deterministic(self):
        workspace = self.setup_workspace()
        task = self.create()
        task.write_text(task.read_text().replace('status: planned','status: wrong')+'\nD-999\n')
        (workspace.data/'roles'/'docs.md').unlink()
        first = self.cli('--root',self.root,'check','all',code=1).stderr
        second = self.cli('--root',self.root,'check','all',code=1).stderr
        self.assertEqual(first,second)
        for rule in ('layout','status','reference-id'):
            self.assertIn(rule,first)
        index = workspace.data/'INDEX.md'
        before = index.read_bytes()
        self.cli('--root',self.root,'index',code=1)
        self.assertEqual(index.read_bytes(),before)


if __name__ == '__main__':
    unittest.main()
