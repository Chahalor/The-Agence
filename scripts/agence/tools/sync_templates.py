"""Stage canonical templates into package resources (run from this repository)."""
from pathlib import Path
import shutil

package = Path(__file__).resolve().parents[1]
canonical = package.parents[1] / 'Workspaces'
templates = package / 'src/agence/templates'
APPENDIX = '''

# Generated index ownership

`.agence/INDEX.md` is generated output. After changing tracked documents, run
`ta index` from the workspace instead of editing the index manually. This
appendix takes precedence over earlier instructions to update the index by hand.
'''


def main():
    (templates / 'roles').mkdir(parents=True, exist_ok=True)
    for role in ('architect', 'coder', 'tester', 'reviewer', 'perfs', 'docs'):
        shutil.copyfile(canonical / f'{role}.md', templates / 'roles' / f'{role}.md')
    (templates / 'AGENTS.md').write_text(
        (canonical / 'AGENTS.md').read_text(encoding='utf-8') + APPENDIX, encoding='utf-8')


if __name__ == '__main__':
    main()
