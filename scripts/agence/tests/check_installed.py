"""Verify an installed ta executable from a clean, unrelated working directory."""
from pathlib import Path
import argparse
import os
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', help='absolute path to installed ta')
    executable = Path(parser.parse_args().executable).resolve()
    env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    with tempfile.TemporaryDirectory(prefix='ta installed ') as directory:
        root = Path(directory) / 'fresh project'

        def run(*arguments):
            result = subprocess.run([str(executable), *map(str, arguments)], cwd=directory,
                                    env=env, text=True, capture_output=True, check=True)
            return result.stdout

        assert 'usage:' in run('--help')
        run('setup', root)
        for role in ('architect','coder','tester','reviewer','perfs','docs'):
            assert (root/'.agence'/'roles'/f'{role}.md').is_file()
        assert 'Generated index ownership' in (root/'AGENTS.md').read_text()
        run('--root', root, 'new', 'work', 'Installed work', '--status', 'active')
        for kind in ('decision','note','report'):
            run('--root', root, 'new', kind, f'Installed {kind}', '--related', 'T-001')
        run('--root', root, 'check', 'all')
        run('--root', root, 'index')
        assert 'T-001' in run('--root', root, 'status')
        assert 'owner: coder' in run('--root', root, 'status', 'T-001')
        before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
        run('setup', root)
        assert before == {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    print('Installed CLI workflow passed outside repository.')


if __name__ == '__main__':
    main()
