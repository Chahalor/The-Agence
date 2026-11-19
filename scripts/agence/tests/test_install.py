"""Installation behavior with disposable source and Codex directories.

TA_TEST_INSTALLED=1 runs subprocesses against the wheel environment's Python
without injecting source modules through PYTHONPATH.
"""
from argparse import Namespace
from pathlib import Path
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from agence.commands import install
from agence.cli import main
from agence.installing import install_agents
from agence.workspace import AgenceError


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='ta install ')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root/'agents'
        self.source.mkdir()
        self.destination = self.root/'codex user'
        self.env = os.environ.copy()
        if os.environ.get('TA_TEST_INSTALLED') == '1':
            import agence
            self.env.pop('PYTHONPATH', None)
            self.assertIn('site-packages', Path(agence.__file__).parts)
        else:
            self.env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1]/'src')
        for name in ('reviewer', 'tester'):
            (self.source/f'{name}.toml').write_text(f'name = "{name}"\n# Français\n', encoding='utf-8')

    def cli(self, *arguments, code=0):
        result = subprocess.run([sys.executable, '-m', 'agence', *map(str, arguments)],
                                cwd=self.root, env=self.env, capture_output=True,
                                text=True, timeout=20)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        return result

    def snapshot(self):
        return {p.relative_to(self.root): (p.lstat().st_mode, p.lstat().st_mtime_ns,
                os.readlink(p) if p.is_symlink() else p.read_bytes() if p.is_file() else None)
                for p in self.root.rglob('*')}

    def test_force_replaces_only_differing_agents(self):
        installed = self.destination/'agents'
        installed.mkdir(parents=True)
        changed = installed/'reviewer.toml'
        changed.write_bytes(b'old reviewer')
        identical = installed/'tester.toml'
        identical.write_bytes((self.source/'tester.toml').read_bytes())
        original_stat = identical.stat()
        config = self.destination/'config.toml'
        config.write_bytes(b'personal configuration')
        personal = installed/'personal.toml'
        personal.write_bytes(b'personal agent')
        (self.source/'new.toml').write_bytes(b'new agent')
        source_bytes = {p.name: p.read_bytes() for p in self.source.iterdir()}
        result = self.cli('install', '--codex-dir', self.destination, '--force')
        self.assertEqual(result.stdout.count('Replaced '), 1)
        self.assertEqual(result.stdout.count('Installed '), 1)
        self.assertEqual(result.stdout.count('Unchanged '), 1)
        for name, content in source_bytes.items():
            self.assertEqual((installed/name).read_bytes(), content)
            self.assertEqual((self.source/name).read_bytes(), content)
        self.assertEqual(identical.stat().st_ino, original_stat.st_ino)
        self.assertEqual(identical.stat().st_mtime_ns, original_stat.st_mtime_ns)
        self.assertEqual(config.read_bytes(), b'personal configuration')
        self.assertEqual(personal.read_bytes(), b'personal agent')
        self.assertFalse(list(installed.glob('.ta-install-*')))

    def test_force_flag_works_before_and_after_install(self):
        installed = self.destination/'agents'
        installed.mkdir(parents=True)
        for arguments in (('--force', 'install'), ('install', '--force'),
                          ('-f', 'install'), ('install', '-f')):
            with self.subTest(arguments=arguments):
                (installed/'reviewer.toml').write_bytes(b'old agent')
                result = self.cli(*arguments, '--codex-dir', self.destination)
                self.assertIn('Replaced ', result.stdout)
                self.assertEqual((installed/'reviewer.toml').read_bytes(),
                                 (self.source/'reviewer.toml').read_bytes())
        self.cli('--force', 'status', code=2)
        self.cli('install', '--force=false', code=2)

    def test_force_dry_run_reports_replacements_without_writes(self):
        installed = self.destination/'agents'
        installed.mkdir(parents=True)
        (installed/'reviewer.toml').write_bytes(b'old agent')
        before = self.snapshot()
        result = self.cli('install', '--codex-dir', self.destination, '--force', '--dry-run')
        self.assertIn('Would replace ', result.stdout)
        self.assertIn('Would install ', result.stdout)
        self.assertNotIn('Unchanged ', result.stdout)
        self.assertEqual(before, self.snapshot())

    def test_force_rejects_incompatible_targets_without_writes(self):
        installed = self.destination/'agents'
        installed.mkdir(parents=True)
        target = installed/'reviewer.toml'
        outside = self.root/'protected-file'
        outside.write_bytes(b'preserve')
        for kind in ('directory', 'symlink', 'broken-symlink'):
            with self.subTest(kind=kind):
                if kind == 'directory':
                    target.mkdir()
                else:
                    target.symlink_to(outside if kind == 'symlink' else self.root/'absent')
                before = self.snapshot()
                for options in (('--force',), ('--force', '--dry-run')):
                    self.cli('install', '--codex-dir', self.destination, *options, code=1)
                    self.assertEqual(before, self.snapshot())
                if kind == 'directory':
                    target.rmdir()
                else:
                    target.unlink()
        self.assertEqual(outside.read_bytes(), b'preserve')

    def test_force_failed_replace_preserves_old_bytes_and_cleans_staging(self):
        installed = self.destination/'agents'
        installed.mkdir(parents=True)
        target = installed/'reviewer.toml'
        target.write_bytes(b'old complete agent')
        before = self.snapshot()
        for failure in (OSError('replace failed'), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__):
                with patch('agence.installing.os.replace', side_effect=failure):
                    with self.assertRaisesRegex(AgenceError, 'retry ta install --force'):
                        install_agents(self.source, self.destination, force_run=True)
                self.assertEqual(target.read_bytes(), b'old complete agent')
                self.assertEqual(sorted(p.name for p in installed.iterdir()), ['reviewer.toml'])
                # Parent directory mtimes change when staging files are cleaned.
                self.assertEqual(before[target.relative_to(self.root)],
                                 self.snapshot()[target.relative_to(self.root)])

    def test_force_partial_failure_reports_changes_and_retry_recovers(self):
        installed = self.destination/'agents'
        installed.mkdir(parents=True)
        for name in ('reviewer', 'tester'):
            (installed/f'{name}.toml').write_bytes(b'old complete agent')
        real_replace = os.replace
        calls = 0
        def fail_second(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('second replacement failed')
            return real_replace(source, target)
        with patch('agence.installing.os.replace', side_effect=fail_second):
            with self.assertRaisesRegex(AgenceError, 'Replaced: .*reviewer.toml'):
                install_agents(self.source, self.destination, force_run=True)
        self.assertEqual((installed/'reviewer.toml').read_bytes(), (self.source/'reviewer.toml').read_bytes())
        self.assertEqual((installed/'tester.toml').read_bytes(), b'old complete agent')
        self.assertFalse(list(installed.glob('.ta-install-*')))
        retry = self.cli('install', '--codex-dir', self.destination, '--force')
        self.assertEqual(retry.stdout.count('Replaced '), 1)
        self.assertEqual(retry.stdout.count('Unchanged '), 1)

    def test_force_rechecks_destination_after_staging(self):
        installed = self.destination/'agents'
        installed.mkdir(parents=True)
        target = installed/'reviewer.toml'
        target.write_bytes(b'old agent')
        outside = self.root/'protected-file'
        outside.write_bytes(b'preserve')
        def link_after_preflight(fd):
            target.unlink()
            target.symlink_to(outside)
        with patch('agence.installing.os.fsync', side_effect=link_after_preflight):
            with self.assertRaisesRegex(AgenceError, 'incompatible destination'):
                install_agents(self.source, self.destination, force_run=True)
        self.assertTrue(target.is_symlink())
        self.assertEqual(outside.read_bytes(), b'preserve')
        self.assertFalse(list(installed.glob('.ta-install-*')))

    def test_cli_default_source_and_idempotent_install(self):
        invocation = [sys.executable, '-m', 'agence', 'install', '--codex-dir', str(self.destination)]
        first = subprocess.run(invocation, cwd=self.root, env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout.count('Installed '), 2)
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in (self.destination/'agents').iterdir()}
        second = subprocess.run(invocation, cwd=self.root, env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(second.stdout.count('Unchanged '), 2)
        self.assertEqual(before, {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in (self.destination/'agents').iterdir()})
        for path in self.source.iterdir():
            self.assertEqual(path.read_bytes(), (self.destination/'agents'/path.name).read_bytes())

    def test_default_codex_directory_and_dry_run(self):
        home = self.root/'user home'
        args = Namespace(source=str(self.source), codex_dir=None, dry_run=True)
        with patch('agence.commands.Path.home', return_value=home):
            result = install(args)
        self.assertIn(str(home/'.codex'/'agents'/'tester.toml'), result)
        self.assertFalse(home.exists())
        self.assertEqual(result.count('Would install '), 2)

    def test_conflicts_preflight_before_any_copy(self):
        (self.destination/'agents').mkdir(parents=True)
        existing = self.destination/'agents'/'tester.toml'
        existing.write_text('customized')
        with self.assertRaisesRegex(AgenceError, 'existing agent differs'):
            install_agents(self.source, self.destination)
        self.assertEqual(existing.read_text(), 'customized')
        self.assertFalse((self.destination/'agents'/'reviewer.toml').exists())
        with self.assertRaises(AgenceError):
            install_agents(self.source, self.destination, dry_run=True)

    def test_missing_empty_and_symlink_sources_do_not_write(self):
        with self.assertRaises(AgenceError):
            install_agents(self.root/'missing', self.destination)
        for path in self.source.iterdir():
            path.unlink()
        (self.source/'README.md').write_text('ignored')
        (self.source/'nested').mkdir()
        (self.source/'nested'/'agent.toml').write_text('not recursively installed')
        with self.assertRaisesRegex(AgenceError, 'no .toml'):
            install_agents(self.source, self.destination)
        (self.source/'link.toml').symlink_to(self.source/'README.md')
        with self.assertRaisesRegex(AgenceError, 'regular file'):
            install_agents(self.source, self.destination)
        self.assertFalse(self.destination.exists())

    def test_symlink_destination_and_user_config_preserved(self):
        self.destination.mkdir()
        config = self.destination/'config.toml'
        config.write_text('# personalized configuration\n')
        outside = self.root/'outside'
        outside.mkdir()
        (self.destination/'agents').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(AgenceError):
            install_agents(self.source, self.destination)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(config.read_text(), '# personalized configuration\n')

    def test_partial_failure_keeps_complete_files_and_retry_recovers(self):
        real_link = os.link
        calls = 0
        def fail_second(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('publication failed')
            return real_link(source, target)
        with patch('agence.installing.os.link', side_effect=fail_second):
            with self.assertRaisesRegex(AgenceError, 'Installed: .*reviewer.toml'):
                install_agents(self.source, self.destination)
        installed = self.destination/'agents'
        self.assertEqual(sorted(p.name for p in installed.iterdir()), ['reviewer.toml'])
        result = install_agents(self.source, self.destination)
        self.assertIn('Installed ', result)
        self.assertIn('Unchanged ', result)
        self.assertEqual(sorted(p.name for p in installed.iterdir()), ['reviewer.toml', 'tester.toml'])

    def test_publication_race_never_overwrites_existing_file(self):
        def competing_install(source, target):
            target.write_bytes(b'concurrent customized agent')
            raise FileExistsError()
        with patch('agence.installing.os.link', side_effect=competing_install):
            with self.assertRaisesRegex(AgenceError, 'destination changed'):
                install_agents(self.source, self.destination)
        self.assertEqual((self.destination/'agents'/'reviewer.toml').read_bytes(), b'concurrent customized agent')
        self.assertEqual(list((self.destination/'agents').glob('.ta-install-*')), [])

    def test_install_help_and_argument_errors_are_read_only(self):
        before = self.snapshot()
        help_text = self.cli('install', '--help').stdout
        for option in ('SOURCE', '--codex-dir', '--dry-run'):
            self.assertIn(option, help_text)
        for arguments in (('install', '--codex-dir'),
                          ('install', 'one', 'two'), ('install', '--unknown')):
            with self.subTest(arguments=arguments):
                result = self.cli(*arguments, code=2)
                self.assertEqual(result.stdout, '')
                self.assertIn('usage:', result.stderr)
        self.assertEqual(before, self.snapshot())

    def test_explicit_relative_paths_ignore_root_and_need_no_workspace(self):
        selected = self.root/'source with spaces'
        self.source.rename(selected)
        source_before = {p.name: p.read_bytes() for p in selected.iterdir()}
        result = self.cli('--root', self.root/'uninitialized workspace', 'install',
                          selected.name, '--codex-dir', self.destination.name)
        self.assertEqual(result.stdout.count('Installed '), 2)
        self.assertEqual(result.stderr, '')
        for name, content in source_before.items():
            self.assertEqual((self.destination/'agents'/name).read_bytes(), content)
            self.assertEqual((selected/name).read_bytes(), content)
        self.assertFalse((self.root/'uninitialized workspace').exists())
        self.assertFalse((self.root/'.agence').exists())

    def test_default_destination_installs_into_temporary_home_codex_directory(self):
        home = self.root/'temporary home'
        out, err = StringIO(), StringIO()
        # Redirect Path.home in-process; the real personal directory is untouched.
        with patch('agence.commands.Path.home', return_value=home), \
                redirect_stdout(out), redirect_stderr(err):
            code = main(['--root', str(self.root/'ignored root'), 'install', str(self.source)])
        self.assertEqual(code, 0, err.getvalue())
        self.assertEqual(err.getvalue(), '')
        self.assertEqual(out.getvalue().count('Installed '), 2)
        installed = home/'.codex'/'agents'
        for source in self.source.iterdir():
            self.assertEqual((installed/source.name).read_bytes(), source.read_bytes())
        self.assertFalse((self.root/'ignored root').exists())

    def test_source_selection_ignores_other_extensions_and_nested_definitions(self):
        (self.source/'README.md').write_text('ignored')
        (self.source/'agent.toml.bak').write_text('ignored backup')
        nested = self.source/'nested'
        nested.mkdir()
        (nested/'nested.toml').write_text('not recursively installed')
        self.cli('install', '--codex-dir', self.destination)
        self.assertEqual(sorted(p.name for p in (self.destination/'agents').iterdir()),
                         ['reviewer.toml', 'tester.toml'])

    def test_dry_run_preserves_full_tree_with_missing_and_mixed_destinations(self):
        before = self.snapshot()
        first = self.cli('install', '--codex-dir', self.destination, '--dry-run')
        self.assertEqual(first.stdout.count('Would install '), 2)
        self.assertEqual(before, self.snapshot())
        existing = self.destination/'agents'
        existing.mkdir(parents=True)
        (existing/'reviewer.toml').write_bytes((self.source/'reviewer.toml').read_bytes())
        (self.destination/'config.toml').write_text('# custom user configuration\n')
        before = self.snapshot()
        second = self.cli('install', '--codex-dir', self.destination, '--dry-run')
        self.assertEqual(second.stdout.count('Would install '), 1)
        self.assertEqual(second.stdout.count('Unchanged '), 1)
        self.assertEqual(before, self.snapshot())

    def test_cli_source_preflight_errors_leave_no_partial_files(self):
        invalid = self.source/'zzz-invalid.toml'
        for kind in ('directory', 'broken symlink'):
            with self.subTest(kind=kind):
                if kind == 'directory':
                    invalid.mkdir()
                else:
                    invalid.symlink_to(self.root/'missing source')
                try:
                    before = self.snapshot()
                    for dry_run in (False, True):
                        options = ('--dry-run',) if dry_run else ()
                        error = self.cli('install', '--codex-dir', self.destination,
                                         *options, code=1)
                        self.assertIn('regular file', error.stderr)
                        self.assertEqual(error.stdout, '')
                        self.assertEqual(before, self.snapshot())
                finally:
                    invalid.rmdir() if invalid.is_dir() else invalid.unlink()

    def test_destination_collision_matrix_preserves_all_existing_paths(self):
        outside = self.root/'outside'
        outside.mkdir()
        (outside/'tester.toml').write_bytes((self.source/'tester.toml').read_bytes())
        for kind in ('codex file', 'codex symlink', 'agents file', 'agents symlink',
                     'target directory', 'target symlink', 'broken target symlink',
                     'different target'):
            with self.subTest(kind=kind):
                codex = self.root/kind
                if kind == 'codex file':
                    codex.write_text('preserve')
                elif kind == 'codex symlink':
                    codex.symlink_to(outside, target_is_directory=True)
                else:
                    codex.mkdir()
                    agents = codex/'agents'
                    if kind == 'agents file':
                        agents.write_text('preserve')
                    elif kind == 'agents symlink':
                        agents.symlink_to(outside, target_is_directory=True)
                    else:
                        agents.mkdir()
                        target = agents/'tester.toml'
                        if kind == 'target directory':
                            target.mkdir()
                        elif kind == 'target symlink':
                            target.symlink_to(outside/'tester.toml')
                        elif kind == 'broken target symlink':
                            target.symlink_to(outside/'missing.toml')
                        else:
                            target.write_text('personalized definition')
                before = self.snapshot()
                for dry_run in (False, True):
                    options = ('--dry-run',) if dry_run else ()
                    result = self.cli('install', '--codex-dir', codex, *options, code=1)
                    self.assertEqual(result.stdout, '')
                    self.assertEqual(before, self.snapshot())

    def test_mixed_install_preserves_config_sources_and_identical_agent(self):
        installed = self.destination/'agents'
        installed.mkdir(parents=True)
        config = self.destination/'config.toml'
        config.write_bytes(b'# customized\r\nmodel = "user-model"\r\n')
        custom = installed/'personal.toml'
        custom.write_bytes(b'name = "personal"\nmodel = "user-model"\n')
        identical = installed/'reviewer.toml'
        identical.write_bytes((self.source/'reviewer.toml').read_bytes())
        tester = self.source/'tester.toml'
        tester.write_bytes(b'name = "tester"\r\nmodel = "chosen-model"\r\n'
                           b'developer_instructions = """\nKeep verbatim.\n"""\n')
        preserved = [config, custom, identical, *self.source.iterdir()]
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_ino) for p in preserved}
        result = self.cli('install', '--codex-dir', self.destination)
        self.assertEqual(result.stdout.count('Installed '), 1)
        self.assertEqual(result.stdout.count('Unchanged '), 1)
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns,
                                      p.stat().st_ino) for p in preserved})
        self.assertEqual((installed/'tester.toml').read_bytes(), tester.read_bytes())

    @unittest.skipIf(os.name != 'posix' or getattr(os, 'geteuid', lambda: 0)() == 0,
                     'requires POSIX permissions enforced for a non-root user')
    def test_unreadable_source_fails_preflight_before_any_install(self):
        unreadable = self.source/'tester.toml'
        unreadable.chmod(0)
        try:
            for dry_run in (False, True):
                options = ('--dry-run',) if dry_run else ()
                result = self.cli('install', '--codex-dir', self.destination, *options, code=1)
                self.assertIn('Permission denied', result.stderr)
                self.assertEqual(result.stdout, '')
                self.assertFalse(self.destination.exists())
        finally:
            unreadable.chmod(0o600)
        self.cli('install', '--codex-dir', self.destination)

    @unittest.skipIf(os.name != 'posix' or getattr(os, 'geteuid', lambda: 0)() == 0,
                     'requires POSIX permissions enforced for a non-root user')
    def test_unwritable_destination_reports_failure_and_retry_recovers(self):
        installed = self.destination/'agents'
        installed.mkdir(parents=True)
        installed.chmod(0o555)
        try:
            before = self.snapshot()
            result = self.cli('install', '--codex-dir', self.destination, code=1)
            self.assertIn('Installation incomplete', result.stderr)
            self.assertIn('Installed: none', result.stderr)
            self.assertIn('retry ta install', result.stderr)
            self.assertEqual(result.stdout, '')
            self.assertEqual(before, self.snapshot())
        finally:
            installed.chmod(0o755)
        self.cli('install', '--codex-dir', self.destination)

    def test_fsync_failure_and_interrupt_preserve_complete_files_and_retry(self):
        for failure in (OSError('disk synchronization failed'), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__):
                codex = self.root/type(failure).__name__
                real_fsync = os.fsync
                calls = 0

                def fail_second(fd):
                    nonlocal calls
                    calls += 1
                    if calls == 2:
                        raise failure
                    return real_fsync(fd)

                out, err = StringIO(), StringIO()
                with patch('agence.installing.os.fsync', side_effect=fail_second), \
                        redirect_stdout(out), redirect_stderr(err):
                    code = main(['install', str(self.source), '--codex-dir', str(codex)])
                self.assertEqual(code, 1)
                self.assertEqual(out.getvalue(), '')
                self.assertNotIn('Traceback', err.getvalue())
                complete = codex/'agents'/'reviewer.toml'
                self.assertIn(f'Installed: {complete}', err.getvalue())
                self.assertIn('retry ta install', err.getvalue())
                self.assertEqual(complete.read_bytes(), (self.source/'reviewer.toml').read_bytes())
                self.assertEqual([p.name for p in complete.parent.iterdir()], ['reviewer.toml'])
                before = (complete.read_bytes(), complete.stat().st_mtime_ns)
                retry = self.cli('install', '--codex-dir', codex)
                self.assertEqual(retry.stdout.count('Installed '), 1)
                self.assertEqual(retry.stdout.count('Unchanged '), 1)
                self.assertEqual(before, (complete.read_bytes(), complete.stat().st_mtime_ns))

    def test_identical_publication_race_is_idempotent(self):
        def competing_identical_install(source, target):
            target.write_bytes(Path(source).read_bytes())
            raise FileExistsError()

        with patch('agence.installing.os.link', side_effect=competing_identical_install):
            result = install_agents(self.source, self.destination)
        self.assertEqual(result.count('Unchanged '), 2)
        self.assertNotIn('Installed ', result)
        self.assertEqual(sorted(p.name for p in (self.destination/'agents').iterdir()),
                         ['reviewer.toml', 'tester.toml'])
        for path in self.source.iterdir():
            self.assertEqual(path.read_bytes(), (self.destination/'agents'/path.name).read_bytes())

    def test_concurrent_cli_installs_publish_only_complete_identical_files(self):
        invocation = [sys.executable, '-m', 'agence', 'install', str(self.source),
                      '--codex-dir', str(self.destination)]
        processes = []
        try:
            for _ in range(4):
                processes.append(subprocess.Popen(invocation, cwd=self.root, env=self.env,
                                 text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
            for process in processes:
                out, err = process.communicate(timeout=20)
                self.assertEqual(process.returncode, 0, out + err)
                self.assertEqual(err, '')
                self.assertEqual(out.count('Installed ') + out.count('Unchanged '), 2)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.communicate()
        installed = self.destination/'agents'
        self.assertEqual(sorted(p.name for p in installed.iterdir()),
                         ['reviewer.toml', 'tester.toml'])
        for source in self.source.iterdir():
            self.assertEqual((installed/source.name).read_bytes(), source.read_bytes())

    def test_repository_definitions_are_copied_verbatim_to_disposable_target(self):
        source = Path(__file__).resolve().parents[3]/'agents'
        definitions = sorted(source.glob('*.toml'))
        self.assertTrue(definitions, 'repository must provide standalone agent definitions')
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in definitions}
        self.cli('install', source, '--codex-dir', self.destination)
        self.assertEqual(sorted(p.name for p in (self.destination/'agents').iterdir()),
                         [p.name for p in definitions])
        for path in definitions:
            self.assertEqual((self.destination/'agents'/path.name).read_bytes(), before[path][0])
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before[path])


if __name__ == '__main__':
    unittest.main()
