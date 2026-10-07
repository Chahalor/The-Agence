---
schema: agence/work/v1
id: T-002
title: Implement agence Python CLI
status: review
owner: reviewer
tags: [cli, implementation, plan]
related: [D-001, N-001]
---

# Implement agence Python CLI

## Goal

Implement every tool described in `scripts/agence/README.md`, using the document
formats in `docs/workspace.md`. Deliver an installable `ta` command that can
initialize a project, validate its coordination files, create documents,
generate its index and display its state.

## Constraints

- Python implementation; retain the README command names and subcommands.
- Follow D-001. Keep Markdown/YAML authoritative and use only existing tA types.
- Preserve existing project content, custom role definitions and task history.
- This mission currently contains an architecture plan; no CLI exists yet.
- Command syntax and defaults below resolve README omissions. They do not remove
  any requested capability. Examples below are target behavior, not runnable now.
- Keep implementation and its packaging/tests inside `scripts/agence/`.
  Only the narrowly required index-ownership update may change
  `scripts/AGENTS.md`; reusable template adjustments must be explicitly recorded.

## Context

- `scripts/agence/README.md`: authoritative feature list and status examples.
- `docs/workspace.md`: schemas, statuses, sections, IDs and directory structure.
- `Workspaces/AGENTS.md`: canonical reusable global rules.
- `Workspaces/`: canonical six core roles.
- `scripts/AGENTS.md`: local workspace rules and temporary bootstrap exception.
- D-001: selected architecture.
- N-001: existing scripts workspace context.

## Current state

2026-10-07: Independent tester validation passed. All 31 existing tests, including
the four reviewer regressions, and 12 new acceptance tests pass (43 total). The
new tests also pass against the built wheel outside the repository; installed
console workflow, dependency consistency and scripts-workspace check-all pass.
Real filesystem permission failures and a controlled SIGINT verify retention,
lock cleanup and recovery. The temporary installed environment uses system
PyYAML because dependency downloads were unavailable; a fully isolated dependency
install and other supported Python versions are unverified. T-002 remains in
review, now owned by reviewer for focused reinspection of the corrections.

## Implementation contract

### 1. Package and module boundaries

Planned layout beneath `scripts/agence/`:

```text
pyproject.toml
README.md
src/agence/
  __init__.py
  __main__.py
  cli.py
  workspace.py
  documents.py
  checks.py
  rendering.py
  commands.py
  templates/
    AGENTS.md
    roles/<role>.md
    work.md
    decision.md
    note.md
    report.md
tests/
```

These paths are proposed deliverables, not existing files.

| Module | Owns |
|---|---|
| `scripts/agence/src/agence/cli.py` | argparse tree, dispatch, stdout/stderr, exit codes |
| `scripts/agence/src/agence/workspace.py` | root discovery, directory paths, template resources, safe writes |
| `scripts/agence/src/agence/documents.py` | schema constants, parsing, catalog, ID/slug allocation |
| `scripts/agence/src/agence/checks.py` | file, directory and reference diagnostics |
| `scripts/agence/src/agence/rendering.py` | deterministic index and status text |
| `scripts/agence/src/agence/commands.py` | orchestration of setup/check/new/index/status |

Commands depend on these helpers; helpers must not depend on command dispatch.
Use simple records for `Workspace`, `Document` and `Diagnostic`. A document holds
path, metadata, Markdown body and parsed activity entries. Diagnostics carry
path, optional line, rule code and readable message; user input failures do not
produce Python tracebacks by default.

Bundle templates as package resources, discoverable through `importlib.resources`.
Use the six core roles: architect, coder, tester, reviewer, perfs and docs.
Copy canonical global/role templates into package resources as a documented
packaging step; ensure the built wheel includes them. A global template appendix
must state that INDEX.md is generated with `ta index`, rather than edited by
hand. Preserve canonical template content and record any deliberate differences.
Do not copy the scripts-specific context section into newly initialized projects.

### 2. CLI and root resolution

```text
ta [--root PATH] setup [PATH]
ta [--root PATH] check file FILE
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

`--tag` and `--related` are repeatable. All commands and subcommands expose help.
`--root` explicitly selects a project/workspace directory or its .agence/.
Without it, project commands search upward from cwd and select the nearest
.agence/. An explicit check path takes precedence as the check target.
`check file` can validate standalone document syntax without an initialized
workspace. Commands requiring a workspace fail clearly when none exists.

`setup PATH` initializes exactly PATH; without PATH use `--root`, otherwise cwd.
If both setup PATH and `--root` are supplied, require them to resolve to the same
target. Do not infer the setup destination from an ancestor workspace.
`check dir PATH` accepts either .agence/ itself or a directory containing it,
as requested by the README; it never initializes missing directories.

Resolve user-supplied relative paths from cwd. Metadata IDs belong to the chosen
workspace, with no cross-workspace search. For plain source references, use the
enclosing Git repository root when present, otherwise the workspace root; this
supports the existing scripts workspace's repository-relative references.
Markdown relative links resolve from their containing document instead.
Discover Git roots from the filesystem, without requiring network access.

Exit codes: 0 success, 1 validation/operational failure, 2 argument misuse.
Diagnostics go to stderr; requested results and created paths go to stdout.
Status/check commands must not create directories, caches, locks or an index.

### 3. Shared document rules

Use the full status sets from `docs/workspace.md`:

| Type | Prefix / directory | Default status | Allowed statuses |
|---|---|---|---|
| work | T / work | planned | planned, active, blocked, review, completed, cancelled |
| decision | D / knowledge/decisions | proposed | proposed, accepted, rejected, deprecated, superseded |
| note | N / knowledge/notes | draft | draft, current, outdated, superseded |
| report | R / knowledge/reports | draft | draft, final, obsolete |

Names follow PREFIX-NNN-slug.md; NNN has at least three decimal digits and may
expand beyond 999. Require matching filename prefix, metadata ID, document type,
location and `schema: agence/<type>/v1`. Validate common metadata fields:
`schema`, `id`, `title`, `status`, `tags`, `related`. Title is a nonempty string;
tags and related are lists of nonempty strings; related contains ID-shaped
values. Work also requires owner naming an installed role. Additional fields
are allowed if machine-readable; do not invent mandatory fields.

Reject duplicate YAML keys, non-mapping frontmatter, malformed YAML, missing
frontmatter delimiters, duplicate workspace IDs and type/status mismatches.
Read YAML safely; reject executable tags. Schema validation checks syntax/types;
reference existence belongs to `check refs`, and `check all` combines both.

Required sections: work has Goal, Constraints, Context, Current state, Activity;
decision has Decision, Rationale, Consequences, References; note has Summary.
Report templates use Objective, Method, Results, Findings, Recommendations,
References from the specification, without asserting these are mandatory schema
fields. Roles and AGENTS/INDEX are not T/D/N/R documents and do not require
structured-document frontmatter. Ignore `.gitkeep` and code files when building
the document catalog, but diagnose unexpected Markdown in document directories.

### 4. Command behavior and README acceptance mapping

| README tool | Required behavior | Acceptance evidence |
|---|---|---|
| setup | Create AGENTS.md, INDEX.md, six roles, work and three knowledge directories | Fresh target matches architecture; repeated setup preserves existing content |
| check file | Check document filename, YAML metadata and applicable section rules | Valid documents pass; precise diagnostics for bad filename/schema/status/YAML |
| check dir | Check direct coordination directory or nested .agence/ architecture | Both path forms pass; missing directory/global rules/roles/index reported |
| check refs | Check document IDs and local file/link targets | Existing references pass; missing IDs/files/anchors and ambiguous IDs fail |
| check all | Aggregate directory, file and reference checks | All findings reported in deterministic path/rule order; nonzero on errors |
| new work/decision/note/report | Create correctly named, typed documents from templates | All four types have valid metadata, IDs and prescribed sections |
| index | Regenerate a concise INDEX.md from source metadata | Stable output, working links, terminal work omitted from active table |
| status | Display live work table and knowledge counts | README overview columns and counts present |
| status ID_OR_FILE | Display selected document metadata and latest activity | README's `T-014` example detail shape supported; unknown/ambiguous selection fails |

**setup:** preflight required destinations and reject incompatible file/directory
collisions before writes. Create missing files only, preserving existing AGENTS
and role files. Generate the index from a valid catalog; do not replace an
existing index if catalog validation fails. No force overwrite mode is needed
for V0. New global instructions describe generated index ownership; for an
existing project, report any required instruction change rather than rewriting
its customized rules. A partial failure must name what was created and what
remains; retries safely fill gaps.

**new:** require an existing structurally usable workspace. Default work owner is
coder; an explicit owner must match an installed role. Allocate one more than
the highest numeric ID for that type, including terminal documents. Scan names
and metadata; malformed or duplicate IDs prevent allocation. Normalize titles
to lowercase ASCII kebab slugs, separating non-alphanumeric runs, removing
empty edge separators; reject titles with no usable slug. Serialize title/tags
with YAML rather than string interpolation. Related IDs must resolve before
creation. Fill sections with clear placeholders; Activity starts empty.
Print the created document path and regenerate the index. Do not overwrite an
existing document or allocate IDs from INDEX.md.

**reference checking:** inspect `related`, standalone T/D/N/R IDs, Markdown inline
and reference-style links, and inline-code source paths (optional `:line`).
Ignore fenced code blocks, examples inside code, external URLs and generic code
expressions; distinguish paths by a slash or a known document/file suffix.
Validate paths and positive in-range line references; plain directory references
may resolve to directories. Support URL decoding in link paths, image targets,
relative links and fragments. Local fragments use lowercase heading slugs with
punctuation removed, whitespace hyphenated, and duplicate suffixes `-1`, `-2`.
ID-shaped filenames must not also generate an accidental bare-ID diagnostic.
Missing or duplicate IDs fail; reference cycles and self references are allowed.
Never fetch external links. Report unsupported local link syntax explicitly
instead of silently treating it as validated. Test the supported syntax using
real tA examples, including paths with spaces and fenced examples.

**index:** render from validated documents, sorted by type and numeric ID. Active
work includes planned, active, blocked and review; completed/cancelled work may
be omitted. Decisions include proposed/accepted; notes include draft/current;
reports include draft/final. Label entries with status and relative Markdown
links. Escape Markdown titles, table delimiters and line breaks. Include a
generated-file notice and regeneration command; omit volatile timestamps.
Empty sections remain readable. Running twice without source changes produces
identical bytes; malformed source documents leave an existing index untouched.

**status:** use the catalog directly, not the index. Overview includes nonterminal
work with ID/status/owner/title and total document counts per knowledge type,
including historical statuses. Show explicit empty states. A selected work item
shows ID/title, status, owner, related IDs and last Activity entry (including a
handoff heading and its body). For knowledge documents show ID/title/status and
related IDs; show no-activity text where appropriate. Wrap long titles cleanly,
keep output readable when redirected, and do not require ANSI colors.

### 5. Write and failure semantics

Check/status are read-only. Mutation destinations stay within the selected
workspace; reject symlinked managed destinations that redirect outside it.
References may read existing repository files outside a nested workspace.
Read templates from package resources without mutating their source.

Use exclusive file creation for new documents; if another process allocates the
same numeric ID under a different slug, exclusive filename creation alone is
insufficient. Serialize mutating commands with a transient workspace lock
(created exclusively, cleaned up in finally), including ID allocation and index
publication. A held lock fails clearly; do not silently delete a suspected stale
lock. This is synchronization, not a new persistent tA object type.

Replace INDEX.md through a temporary sibling and atomic rename. Validate before
writing. A document creation followed by an index failure retains the document,
returns an error, names its path and directs recovery with `ta index`; never
report full success or delete the user's newly created document. Avoid claiming
cross-file transaction guarantees. Setup before a workspace exists must lock the
explicit target without changing an ancestor workspace.

## Delivery sequence

1. **Foundation — coder:** package metadata/entry points/resources, schema
   constants, workspace discovery, parser/catalog and diagnostic contracts.
   Gate: help works from a clean install; YAML and root-resolution fixtures pass.
2. **Validation — coder:** implement check file/dir/refs/all using shared rules.
   Gate: positive and negative fixtures for every check, stable diagnostics,
   read-only behavior and accumulation of errors in check all.
3. **Index and setup — coder:** deterministic renderer, atomic publication,
   templates and idempotent setup. Gate: clean/repeated/partial setup,
   preservation of customized files, conflict handling and stable index output.
4. **Creation — coder:** all four new commands, IDs/slugs/metadata/options,
   mutation locking and automatic index refresh. Gate: all types pass check all,
   related references resolve, IDs expand beyond 999 and collisions are handled.
5. **Status — coder:** overview and selected-document view from live catalog.
   Gate: README-shaped overview/detail, empty states, handoffs, stale index,
   missing/duplicate IDs and malformed documents tested.
6. **Validation and documentation — tester/reviewer/docs:** independent CLI
   integration validation, focused review of writes/reference handling, and
   installation/usage/examples documented in the existing README. Replace the
   local bootstrap index instruction only once the generator works. Run index
   against this scripts workspace without losing durable source information.

Use standard-library unittest with temporary directories and subprocess CLI
integration tests. Validate `setup -> new` for each type `-> check all -> index
-> status -> status ID`, plus malformed metadata, dangling refs, repeated setup,
read-only commands, concurrency/lock cleanup, interruption/failure recovery,
paths containing spaces and installed template availability. Test a built wheel
in a clean temporary environment outside the repository so setup cannot rely
on relative access to `Workspaces/`. Declare build/runtime dependencies and the
verification commands in the README; do not require a global installation.

## Completion criteria

- Every README command and subcommand is implemented and discoverable in help.
- All four document types match the current schema and naming conventions.
- Setup preserves custom content; checks identify schema/layout/reference errors.
- Generated index and live status accurately reflect source documents.
- Relevant tests pass, including clean-install and filesystem failure cases.
- README documents installation, target/root rules, options, exit codes and
  generated index ownership using verified examples.
- Tester/reviewer findings are resolved or explicitly tracked; no independent
  validation is claimed by the coder or architect.
- Current state, activity and index reflect the actual outcome.

## Activity

### note · architect

2026-10-06: User assigned The_Architect to plan the agence script according to
its README. Existing workspace has only the CLI specification and tA agent files.

### decision · architect

Selected a small installable Python CLI with shared document rules, packaged
templates and generated index ownership. Promoted to: D-001.

### result · architect

Mapped every README capability to command behavior, module ownership, ordered
delivery gates and acceptance scenarios. Defined defaults where README is silent.
Checked design against the local agent rules and current document specification.
This is architecture validation, not independent implementation review.

### handoff · architect → coder

Implement this contract in the delivery sequence above when implementation is
assigned. Load D-001 and the authoritative README/schema before coding. Keep
this task planned until execution begins, then active. Record local results and
findings here; hand off to tester for behavioral verification and reviewer for
focused review once the implementation is ready. Do not mark the task completed
merely because the architecture plan exists.

### note · coder

2026-10-06: User assigned The_Coder to implement the Python CLI. Implementation
and local acceptance tests are scoped to the delivery contract above.

### result · coder

2026-10-06: Implemented all README command families and subcommands in
`scripts/agence/src/agence/`, with installable console/module entry points,
shared schema/catalog validation, local reference checks, live status, exclusive
creation, mutation locking and atomic index replacement. Bundled canonical
roles unchanged; the global template adds only generated-index ownership.
Documented installation, commands, root rules and failure recovery in
`scripts/agence/README.md`. The only local global-rule change replaces the
bootstrap index exception with generator ownership.

Local validation:

- 23 unittest cases passed, including subprocess workflows, malformed metadata,
  reference syntax, concurrency, read-only state, symlink rejection, partial
  setup, publication failures and handled interruption cleanup.
- Built the 0.1.0 wheel with setuptools; installed into a clean temporary venv
  with PyYAML 6.0.3. The installed executable completed setup, all four new types,
  check all, index, overview/detail status and repeated setup outside the repo.
- Packaged roles match canonical source files; global resource preserves the
  canonical rules plus the documented ownership appendix.
- Generated the scripts workspace index from validated source metadata.

Verification entry points:

- `scripts/agence/tests/test_cli.py`
- `scripts/agence/tests/check_installed.py`
- `scripts/agence/tools/sync_templates.py`

These are implementation-local checks, not independent tester/reviewer results.

### finding · coder

The existing workspace's planning/context prose contains illustrative IDs and
shorthand filenames that fail the specified reference-existence rules. Examples
include the illustrative task ID `T-014`, the filename pattern
PREFIX-NNN-slug.md, module basenames in this contract's module table, and
workspace-local shorthand .agence/ and INDEX.md in this contract, D-001 and
N-001. Plain source references are deliberately resolved from the enclosing
repository root, so these shorthand paths do not resolve in the nested scripts
workspace. Schema/layout checks pass; reference checks report these findings.

Keep the strict reference contract. Tester/docs should distinguish illustrative
text from real references, then qualify actual source paths or format examples
as fenced blocks when maintaining these documents. Historical context has not
been silently rewritten to hide diagnostics.

### handoff · coder → tester

Implementation is ready for independent behavioral validation under this
contract. Run the README verification commands and exercise the installed CLI.
Review handling of malformed inputs, partial writes, interruptions, locks and
references independently. Existing planning-reference findings above remain
tracked. After validation, hand off to reviewer for focused write/reference
review, then docs for any broader documentation corrections. Do not mark this
task completed until the required independent validation and review are resolved.

### result · coder

2026-10-07: User requested relative check diagnostic paths and an explicit target
directory after every check subcommand. Check diagnostics now use the selected
coordination directory as their display base, including relative resolved-target
paths. Standalone files use cwd if no workspace is found. All four checks accept
workspace directories or their coordination directories; file checks retain
single-document support and now validate the catalog when given a directory.
Reference resolution semantics are unchanged. Updated CLI help and README.

Local validation: 26 tests passed, covering both directory forms for every check,
relative diagnostics, standalone files, explicit-target precedence and read-only
behavior. Built and reinstalled the wheel into the existing project-local venv.
Verified the user's command below; it accepts the target and emits relative
paths, while returning exit 1 for the previously recorded reference findings.

```sh
scripts/agence/.venv/bin/ta check all ./scripts/
```

### handoff · coder → tester

Include the 2026-10-07 check-directory and relative-diagnostic changes in the
pending independent validation. Existing reference-content findings remain
tracked above; no reference rules were relaxed to suppress them.

### result · coder

2026-10-07: Corrected reference formatting after the user reported check-all
findings. The module table now references existing repository-relative source
paths, and D-001 references the actual scripts index. Literal directory names,
filename patterns and the illustrative task ID are identified as examples rather
than live references. N-001 retains its historical directory-layout explanation.
These corrections resolve the earlier reference-content finding; reference
validation rules and independent-review status are unchanged.

Validation: the project-local executable's check all command passes for the
scripts workspace, returning exit code 0. Regenerated the index afterwards.

### finding · reviewer

2026-10-07. Severity: major (P2).

The catalog silently omits symlinked document directories. Layout validation
accepts them because it uses is_dir(), while os.walk() does not descend into
directory symlinks. Moving the work directory to another directory inside the
workspace and replacing it with a symlink makes check-all pass and status report
no active work, despite an existing planned task. Creating a note then succeeds
and publishes an index with that task omitted.

Refs: `scripts/agence/src/agence/documents.py:185`,
`scripts/agence/src/agence/checks.py:18`.

Recommended direction: diagnose excluded symlinked coordination directories so
an incomplete catalog cannot pass validation or replace the index. Preserve the
managed-write symlink restriction rather than simply enabling recursive following.

### finding · reviewer

2026-10-07. Severity: major (P2).

Malformed YAML timestamps escape the parser's error handling. Adding an optional
frontmatter field containing an invalid date causes PyYAML's timestamp
constructor to raise ValueError, which neither parse() nor CLI main() catches.
Check-all aborts with a Python traceback instead of reporting a document
diagnostic and accumulating the remaining findings. Other catalog consumers
are affected as well.

Reproduction input:

```yaml
created: 2026-13-01
```

Refs: `scripts/agence/src/agence/documents.py:110`,
`scripts/agence/src/agence/cli.py:49`.

Recommended direction: convert YAML construction failures into parser diagnostics
and cover invalid timestamp values in the malformed-frontmatter tests.

### finding · reviewer

2026-10-07. Severity: minor (P2).

The inline-link regular expression ignores Markdown escapes. Creating a note
with the title shown below succeeds; the generator escapes its brackets, but
check-refs subsequently interprets the escaped title as a link to a nonexistent
local v2 file. Thus a document created by the CLI fails its own reference checks
even though the heading contains literal text rather than a Markdown link.

Reproduction title:

```text
Fix [API](v2)
```

Refs: `scripts/agence/src/agence/checks.py:132`,
`scripts/agence/src/agence/commands.py:138`.

Recommended direction: honor escaped Markdown delimiters during reference
extraction and verify creation followed by check-all with this title.

### finding · reviewer

2026-10-07. Severity: minor (P2).

External URL detection excludes every scheme-qualified target ending in a
numeric colon suffix. The external link below is consequently interpreted as a
local path with a line number and rejected as a missing file. This contradicts
the external-link exclusion contract and can also cause local file reads when
the parsed absolute path exists.

Reproduction body:

```markdown
[external](https://example.com/tickets/123:42)
```

Refs: `scripts/agence/src/agence/checks.py:59`.

Recommended direction: distinguish bare filename line references from URLs
before parsing line suffixes; do not let a URL suffix override its scheme.

### result · reviewer

2026-10-07: Review result: changes requested. Inspected the CLI, catalog/schema
rules, reference extraction, rendering, write/lock behavior, resources, packaging
and existing tests against D-001 and this task's implementation contract.
Module separation is appropriate, and the normal mutation path uses exclusive
creation, locking and atomic index replacement.

Independent review validation:

- All 26 existing unittest cases passed.
- Source CLI check-all passed for the scripts workspace.
- Built the wheel without fetching dependencies. Installed into a temporary
  venv using system-provided PyYAML; the installed-workflow script passed outside
  the repository with PYTHONPATH cleared. This verifies wheel resources and the
  entry point, not a fresh dependency download or every supported Python version.
- Reproduced all four findings in disposable temporary workspaces.
- No production implementation or tests were changed during review.

### handoff · reviewer → coder

Resolve the four findings above and add regression coverage for the reproduced
conditions. Then return to independent tester validation and focused review.
The existing passing tests do not cover these cases. Keep this task in review
until corrections and required validation are complete.

### result · coder

2026-10-07: Addressed all four findings from the reviewer handoff above.

- Symlinked coordination directories, including broken links and a linked
  coordination root, produce catalog/layout diagnostics. Catalog readers fail
  instead of displaying empty state; new/index refuse incomplete catalogs and
  retain the existing index. Directory symlinks are not recursively followed.
- YAML construction ValueError/OverflowError failures are converted to document
  diagnostics, so check-all accumulates other findings without a traceback.
- Escaped Markdown delimiters are masked before link extraction. The reported
  escaped-title reproduction passes check-all; even-backslash cases still allow
  genuine link detection.
- Scheme detection precedes line-suffix parsing. External URLs with numeric
  suffixes do not perform local existence checks; bare source filename line
  references remain validated.

Changed implementation and regression coverage:

- `scripts/agence/src/agence/documents.py`
- `scripts/agence/src/agence/checks.py`
- `scripts/agence/tests/test_cli.py`
- `scripts/agence/README.md`

Validation: 31 unittest cases passed; wheel build passed; rebuilt package
installed in the project-local venv. The installed workflow passed outside the
repository, and the user's check-all command passed with exit code 0. These are
coder-local results; reviewer findings are ready for independent revalidation.

### handoff · coder → tester

Independently validate the four corrections and their regression coverage.
After behavioral validation, return to reviewer to confirm the reported findings
are resolved. Keep this task in review until required validation is complete.

### result · tester

2026-10-07: User assigned the tester to implement and run T-002 validation.
Established a passing baseline of 31 existing tests, then added 12 independent
acceptance cases in `scripts/agence/tests/test_acceptance.py`, reusing the existing
temporary-workspace/subprocess harness. No production implementation changed.

Added coverage:

- Every allowed lifecycle status, empty state, index visibility and historical
  knowledge counts; selected historical documents remain accessible.
- Setup defaults inside an ancestor workspace, matching explicit root targets,
  custom owners, repeated tags/related IDs, self references and reference cycles.
- Duplicate-ID selection/allocation rejection, failed read commands preserving
  the full coordination tree, accumulated deterministic diagnostics, ignored
  non-Markdown files and unexpected Markdown rejection.
- Filename/metadata consistency, required headings outside fences, optional
  structured metadata, decoded anchors, parenthesized paths, line boundaries,
  directory fragments and binary reference read failures.
- Real POSIX permission failures before document creation, during partial setup
  and during index publication; existing index preservation, retained documents,
  actionable diagnostics, lock cleanup and successful retries.
- Real SIGINT delivered at a controlled publication boundary in a subprocess;
  error exit without traceback, retained document and successful index recovery.
  This uses a patched publication hook for deterministic signal timing; forced
  process termination and arbitrary crash timing are not claimed as tested.

Independent outcomes on Python 3.12.3 / PyYAML 6.0.1:

- Source suite: **43/43 passed**, no skips (19.322 seconds).
- Built wheel successfully; installed into a new temporary venv outside the
  repository. Confirmed agence imports from that venv's site-packages.
- Installed acceptance suite: **12/12 passed**, no skips (6.841 seconds), with
  source PYTHONPATH injection disabled.
- Installed console workflow passed: setup, all four new types, check-all,
  index, overview/detail status and repeated setup outside the repository.
- Installed pip check: no broken requirements. Both source and installed CLI
  check-all passed for the actual scripts workspace.
- Independently reran every reviewer regression: symlinked/broken coordination
  directories, malformed YAML timestamps, escaped Markdown delimiters and
  external scheme URLs with numeric suffixes all behaved as required.
- No new implementation defects found in the executed scope.

Reproduction from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts/agence/src python3 -m unittest discover -s scripts/agence/tests -v
python3 -m pip --disable-pip-version-check wheel --no-cache-dir --no-deps --no-build-isolation --wheel-dir /tmp/agence-t002-wheels ./scripts/agence
python3 -m venv --system-site-packages /tmp/agence-t002-env
/tmp/agence-t002-env/bin/python -m pip --disable-pip-version-check install --no-index --no-deps /tmp/agence-t002-wheels/the_agence-0.1.0-py3-none-any.whl
repository="$PWD"
cd /tmp
PYTHONDONTWRITEBYTECODE=1 TA_TEST_INSTALLED=1 /tmp/agence-t002-env/bin/python -m unittest discover -s "$repository/scripts/agence/tests" -p test_acceptance.py -v
PYTHONDONTWRITEBYTECODE=1 /tmp/agence-t002-env/bin/python "$repository/scripts/agence/tests/check_installed.py" /tmp/agence-t002-env/bin/ta
/tmp/agence-t002-env/bin/python -m pip --disable-pip-version-check check
/tmp/agence-t002-env/bin/ta check all "$repository/scripts/"
```

Environment limitation: PyYAML download attempts returned no matching
distribution. The new venv therefore uses system-site-packages for the already
available PyYAML, while agence itself comes only from the built wheel. This
validates installed code/resources and dependency compatibility, but does not
prove a completely isolated fresh dependency installation. Minimum Python 3.10
and other supported interpreter versions were not available for validation.

### handoff · tester → reviewer

Behavioral validation passed and tests are saved in the workspace.
Reinspect the four corrected findings and associated write/reference handling.
Review the new acceptance coverage and retain the installation/interpreter
limitations above. Keep T-002 in review until independent review is resolved;
the tester has not declared the overall implementation complete.
