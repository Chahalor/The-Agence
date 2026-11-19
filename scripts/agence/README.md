# The_Agence — Agence Python CLI

`ta` manages The Agence Markdown/YAML coordination files. It initializes a
workspace, checks its documents and references, creates work and knowledge,
generates `.agence/INDEX.md`, and displays live status. Documents remain the
source of truth; the CLI does not orchestrate agents or enforce role permissions.

## Installation

Python 3.10 or newer is required. Runtime dependency: PyYAML 6.x. Build
dependencies: setuptools (61 or newer) and wheel. From the repository root:

```sh
python3 -m venv scripts/agence/.venv
scripts/agence/.venv/bin/python -m pip install ./scripts/agence
scripts/agence/.venv/bin/ta --help
```

Activate the environment to use `ta` directly, or keep using the executable's
full path. `python -m agence` exposes the same command tree in that environment.
For development, install with `pip install -e ./scripts/agence`.

## Commands

```text
ta [--root PATH] setup [PATH]
ta install [SOURCE] [--codex-dir PATH] [--dry-run] [--force]
ta [--root PATH] check file FILE_OR_PATH
ta [--root PATH] check dir [PATH]
ta [--root PATH] check refs [FILE_OR_PATH]
ta [--root PATH] check all [PATH]
ta [--root PATH] new work TITLE [--owner ROLE] [--status STATUS] [--tag TAG] [--related ID]
ta [--root PATH] new decision TITLE [--status STATUS] [--tag TAG] [--related ID]
ta [--root PATH] new note TITLE [--status STATUS] [--tag TAG] [--related ID]
ta [--root PATH] new report TITLE [--status STATUS] [--tag TAG] [--related ID]
ta [--root PATH] index
ta [--root PATH] status [ID_OR_FILE]
```

Every command and subcommand supports `--help`. `--root` precedes the command.
All supplied relative paths resolve from the current working directory.

Without `--root`, commands discover the nearest `.agence/` in the current
directory or its ancestors. `--root` selects a workspace directory or its
`.agence/` explicitly. An explicit check path takes precedence as the target;
Every check subcommand accepts a workspace directory or its `.agence/` after
the check name, for example `ta check all ./scripts/` or
`ta check file ./scripts/.agence/`. `check file` also accepts a single structured
document and can validate it without an initialized workspace. Target arguments
resolve from the current directory; diagnostic paths are relative to the selected
`.agence/`, including `../AGENTS.md` for global rules. Standalone file diagnostics
use the current directory when no workspace exists.

`setup PATH` initializes exactly that destination. With no PATH it uses
`--root`, then the current directory; it does not choose an ancestor workspace.
If both PATH and `--root` are supplied, they must identify the same destination.

### Install Codex agents

From the repository root:

```sh
scripts/agence/.venv/bin/ta install
```

This copies the regular `.toml` files from `./agents` into `~/.codex/agents/`,
the personal-agent location documented in the
[official Codex documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents).
No workspace initialization is required. The source is a filesystem directory,
not a bundled package resource; pass its path when running elsewhere:

```sh
ta install /path/to/The_Agence/agents
ta install ./agents --dry-run
ta install ./agents --force --dry-run
ta install ./agents --force
ta install ./agents --codex-dir /tmp/example-codex
```

`--codex-dir` selects the Codex root; files go into its `agents` subdirectory.
The default is always `~/.codex`. `--root` does not select installation paths.
Other source file types and nested definitions are ignored; entries named
`.toml` must be regular files. Contents and filenames are
preserved; agent definitions and models are not rewritten. Existing identical
files are left untouched, including with `--force`. By default, a different
existing file fails before any copies begin. `--force` (or `-f`) authorizes
atomic replacement of differing regular agent files with the source contents.
It works before or after `install`; other commands reject this option. Symlinks
and incompatible paths still fail, even in force mode. Personal agents absent
from the source and the Codex configuration remain untouched.

`--dry-run` runs the same preflight without creating files or directories;
combined with `--force`, it distinguishes `Would replace`, `Would install` and
`Unchanged`. Successful writes report `Replaced` or `Installed`. A publication
failure reports the files already installed/replaced and retains completed
changes; there is no batch rollback. Replacement is atomic per file: a failed
publication keeps that file's old contents. Retry with the same options after
fixing the cause.

### Initialize a project

```sh
ta setup /tmp/example-project
```

Setup creates `AGENTS.md`, `.agence/INDEX.md`, six core role definitions and the
work/knowledge directories. Existing instructions, roles and documents are
preserved. Repeated setup fills missing files and regenerates the index. It
preflights incompatible file/directory collisions, and reports partial failures
with created paths. A customized existing `AGENTS.md` is preserved; setup reports
when its instructions need to be updated to use `ta index`.

### Create documents

```sh
ta --root /tmp/example-project new work "Implement parser" --owner coder --status active --tag parser
ta --root /tmp/example-project new decision "Use UTF-8" --status accepted --related T-001
ta --root /tmp/example-project new note "Parser behavior" --related T-001
ta --root /tmp/example-project new report "Parser validation" --related T-001
```

Titles are quoted shell arguments. `--tag` and `--related` are repeatable.
Related IDs must already exist in the selected workspace. Work defaults to
owner `coder`; custom owners must have a role Markdown file in `.agence/roles/`.

| Type | ID / directory | Default status | Allowed statuses |
|---|---|---|---|
| work | T / work | planned | planned, active, blocked, review, completed, cancelled |
| decision | D / knowledge/decisions | proposed | proposed, accepted, rejected, deprecated, superseded |
| note | N / knowledge/notes | draft | draft, current, outdated, superseded |
| report | R / knowledge/reports | draft | draft, final, obsolete |

Names use `PREFIX-NNN-slug.md`, with lowercase ASCII slugs derived from titles.
IDs increment beyond the highest existing numeric ID of that type, including
historical documents, and expand beyond three digits when necessary. Invalid or
duplicate documents prevent allocation. New files contain valid metadata and
section placeholders for the agent to fill; the work Activity section is empty.
Each successful creation refreshes the index and prints the created absolute path.

### Validate a workspace

```sh
ta --root /tmp/example-project check file /tmp/example-project/.agence/work/T-001-implement-parser.md
ta check dir /tmp/example-project/.agence
ta check file /tmp/example-project
ta check refs /tmp/example-project
ta check all /tmp/example-project
```

`file` checks names, safe YAML frontmatter, schemas, metadata types, statuses and
required sections. Duplicate YAML keys, malformed YAML timestamp values and executable YAML tags
are rejected with document diagnostics.
With workspace context, it also checks document placement and work owners.
Additional machine-readable metadata is allowed. Reports have conventional
section templates but no mandatory body sections.

`dir` checks the coordination layout, global rules, index and six core roles.
`refs` checks related IDs, bare document IDs in prose, inline-code source paths,
Markdown inline links, images and reference-style links. `all` accumulates layout,
file and reference diagnostics in stable order. Code and `.gitkeep` files are
ignored by the document catalog; unexpected Markdown is diagnosed. Symlinked
coordination directories are rejected by layout/catalog validation so an
incomplete catalog cannot be displayed as valid or published to the index.

Plain source paths resolve from the enclosing Git repository root, or the
workspace root when no Git repository exists. Markdown links resolve from their
containing document. For example, in a nested `scripts/` workspace, use
`docs/workspace.md` for a repository file and `scripts/.agence/INDEX.md` for the
local index. Filenames on their own still resolve from the source root.

Supported references include:

```markdown
T-001
`src/parser.py:42`
`folder with spaces/source.md`
[source](../../src/parser.py)
[heading](../../README.md#installation)
[space](<../../folder with spaces/source.md>)
[reference][source]
[source]: ../../src/parser.py "Parser source"
```

Line references must be positive and in range. Heading anchors lowercase text,
remove punctuation, hyphenate whitespace and suffix duplicates with `-1`, `-2`.
Link paths and fragments support URL decoding. Use angle brackets for link paths
with spaces or parentheses. Unsupported local link syntax, including local query
strings, produces a diagnostic. External URLs are never fetched or interpreted as local line references,
including URLs whose last component ends with a numeric colon suffix. Escaped
Markdown delimiters remain literal text during link extraction. Fenced examples
and generic inline-code expressions are ignored; put illustrative IDs in code
when they do not refer to actual documents. Missing and ambiguous IDs fail;
cycles and self references are permitted.

### Generate the index

```sh
ta --root /tmp/example-project index
```

The index is generated output: run this after manually changing document
metadata. Do not edit it by hand. It lists active work and current knowledge,
with statuses and working relative links, ordered by numeric ID. Terminal work
and historical knowledge are omitted from the index but retained on disk.
Repeated generation without source changes produces identical bytes. Invalid
source documents leave the existing index untouched. `index` can recover a
missing index.

### View live status

```sh
ta --root /tmp/example-project status
ta --root /tmp/example-project status T-001
```

Example overview:

```text
example-project

Work
────────────────────────────────────────────────────────────────
T-001    active     coder        Implement parser

Knowledge
────────────────────────────────────────────────────────────────
Decisions  1
Notes      1
Reports    1
```

Example selected work after an agent appends a handoff:

```text
T-001 — Implement parser

status: review
owner: tester

related:
  D-001

last activity:
  handoff · coder → tester
  Implementation ready for validation.
```

Status reads current source documents, including historical knowledge counts,
and does not depend on index content. Unknown/ambiguous selections and invalid
catalogs fail clearly. A selected file path must identify a catalog document.
Check and status commands do not write workspace files or an index.

## Failures and write safety

Exit codes: **0** success, **1** validation or operational failure, **2** argument
misuse. Requested output goes to stdout; diagnostics go to stderr without Python
tracebacks. Checks report every finding in deterministic path/rule order.

Mutations serialize through a transient `.agence.lock` in the selected workspace
root, cleaned up on ordinary failures and handled interruptions. A held lock
fails clearly. A forcibly killed process can leave a lock; inspect the holder
before manually removing it. Managed writes reject symlinked destinations and
stay inside the chosen workspace. Reference checks may read repository files
outside a nested workspace.

Index publication uses a temporary sibling followed by atomic replacement.
There is no cross-file transaction: if a document was created but index refresh
failed, it is retained, the command returns an error naming its path, and recovery
is `ta index` after fixing the cause. Setup similarly reports partial progress
and can be retried safely.

## Development and verification

From the repository root, with PyYAML installed:

```sh
PYTHONPATH=scripts/agence/src python3 -m unittest discover -s scripts/agence/tests -v
python3 -m pip wheel --no-deps --no-build-isolation --wheel-dir /tmp/agence-wheels ./scripts/agence
python3 -m venv /tmp/agence-clean-env
/tmp/agence-clean-env/bin/python -m pip install /tmp/agence-wheels/the_agence-0.1.0-py3-none-any.whl
python3 scripts/agence/tests/check_installed.py /tmp/agence-clean-env/bin/ta
```

The installed-workflow test clears `PYTHONPATH` and runs outside the repository,
so setup must use bundled resources. Unit/integration tests cover all command
families, malformed metadata, references, preservation, deterministic output,
read-only behavior, concurrent allocation, locks and publication failures.
These are coder-local checks; independent tester/reviewer validation is a
separate tracked step.

Canonical global/role templates come from `Workspaces/`. Stage updates with
`python3 scripts/agence/tools/sync_templates.py` before building a distribution.
The six roles are exact copies. The bundled global file preserves canonical
content and appends a generated-index ownership rule; it excludes scripts-local
context. Work/decision/note/report templates follow `docs/workspace.md`.
