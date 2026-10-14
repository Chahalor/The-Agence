---
schema: agence/work/v1
id: T-003
title: Install Codex agents
status: review
owner: reviewer
tags: [cli, installation, codex]
related: [T-002]
---

# Install Codex agents

## Goal

Add a ta install command to copy standalone Codex agent definitions from the
repository's `agents/` directory to the user's personal Codex agents directory.

## Constraints

Preserve source contents, filenames, models and existing user configuration.
Do not overwrite differing installed definitions. Installation must not depend
on an initialized tA workspace or alter agent role files.

## Context

- `agents/`: source definitions for perf, reviewer and tester.
- `scripts/agence/README.md`: command syntax and filesystem behavior.
- `scripts/agence/src/agence/installing.py`: dedicated installation helper.
- Official custom-agent location/schema verified in OpenAI documentation.

## Current state

2026-10-14: Independent tester validation passed. Added 14 tests to the seven
existing install cases; the full source suite passes 64/64, without skips.
All 21 install tests also pass against a newly built wheel in a temporary venv
outside the repository, with source PYTHONPATH injection disabled. Installed
console workflow and dependency consistency checks pass. All installation
destinations were disposable, including the redirected default-home test;
the real personal Codex directory was not modified. Ready for independent
review; task remains in review, now owned by reviewer.

## Activity

### note · coder

2026-10-14: User requested an install command for definitions in the repository's
agents directory. The command defaults to that directory relative to cwd and the
standard personal Codex directory; explicit source/target options support other
working directories and isolated tests.

### result · coder

Added install command help, orchestration and helper, with a dry-run option,
preflight conflict checks, idempotent identical-file handling, exclusive atomic
publication and partial-failure diagnostics. Global Codex config is not rewritten.
Added seven tests covering command defaults, preservation, collisions, symlinks,
partial failures and concurrent publication. Extended the installed executable
workflow to exercise dry-run, installation and reinstallation.

Validation: 50 tests passed; wheel build passed; updated project-local venv.
Installed executable workflow passed with source PYTHONPATH removed. Real source
dry-run lists exactly three expected files. No independent validation is claimed.

### handoff · coder → tester

Validate installation semantics and failure recovery independently, including
preservation of existing agents/config, CLI path options and source selection.
Then hand off for review when appropriate.

### result · tester

2026-10-14: User requested the necessary tests for the new install command.
Baseline: all seven existing install tests passed. Extended
`scripts/agence/tests/test_install.py` with 14 behavioral cases, shared CLI/tree
snapshot helpers and an installed-wheel test mode. No production code changed.

New coverage:

- Help and argument errors; default personal destination redirected into a
  temporary home; explicit relative paths with spaces; ignored root selection;
  operation without an initialized workspace.
- Selection of top-level TOML definitions, ignoring nested/other file types;
  source-directory entries and broken symlinks rejected before any copies.
- Dry-run tree preservation for fresh and mixed destinations; byte-for-byte
  preservation of filenames, CRLF, model settings and instructions; source,
  existing identical-agent inode/mtime, personal agents and config preservation.
- Preflight matrix for file/directory collisions, symlinked roots/directories,
  linked definitions, broken destination links and differing existing contents.
- Real unreadable-source and unwritable-destination permission failures, clean
  failure output, no partial publication and successful retry.
- Injected fsync failure and KeyboardInterrupt after one successful publication:
  complete files retained, temporary files removed, partial results reported on
  stderr, exit 1 without traceback, and retry preserves the first installed file.
- Identical competing publication, complementing the existing differing-file
  race test; four real concurrent CLI installations producing complete files.
- The actual repository definitions copied verbatim into a disposable target.

Observed results on Python 3.12.3 / PyYAML 6.0.1:

- Full source suite: **64/64 passed**, no skips, 38.995 seconds.
- Freshly built wheel installed outside the repository. Confirmed agence imports
  from the temporary venv's site-packages, not the source directory.
- Installed install suite: **21/21 passed**, no skips, 4.674 seconds.
- Installed console workflow passed, including install dry-run, initial install
  and repeated install; pip check reported no broken requirements.
- Workspace check-all passed before updating this result.
- No product defect found in the executed scope.

Reproduction from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts/agence/src python3 -m unittest discover -s scripts/agence/tests -p test_install.py -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts/agence/src python3 -m unittest discover -s scripts/agence/tests -v
validation_dir=$(mktemp -d /tmp/agence-install-check-XXXXXX)
python3 -m pip --disable-pip-version-check wheel --no-cache-dir --no-deps --no-build-isolation --wheel-dir "$validation_dir/wheels" ./scripts/agence
python3 -m venv --system-site-packages "$validation_dir/env"
"$validation_dir/env/bin/python" -m pip --disable-pip-version-check install --no-index --no-cache-dir --no-deps "$validation_dir/wheels/the_agence-0.1.0-py3-none-any.whl"
project_path="$PWD"
cd /tmp
PYTHONDONTWRITEBYTECODE=1 TA_TEST_INSTALLED=1 "$validation_dir/env/bin/python" -m unittest discover -s "$project_path/scripts/agence/tests" -p test_install.py -v
PYTHONDONTWRITEBYTECODE=1 "$validation_dir/env/bin/python" "$project_path/scripts/agence/tests/check_installed.py" "$validation_dir/env/bin/ta"
"$validation_dir/env/bin/python" -m pip --disable-pip-version-check check
```

Limits: the temporary venv uses system-provided PyYAML; this is installed-wheel
validation, not a fresh isolated dependency download. Other Python/platform
versions were not exercised. Interruption was injected at fsync via
KeyboardInterrupt; arbitrary OS signal/crash timing is not claimed as tested.
The concurrent subprocess test starts four installers but does not force a
specific scheduler interleaving; controlled publication races are tested
separately. Actual personal Codex configuration was not used as a fixture.

### handoff · tester → reviewer

Behavioral validation passed and coverage is saved in
`scripts/agence/tests/test_install.py`. Review the install command's preflight,
exclusive publication, preservation and failure cleanup. Retain the test limits
above; keep T-003 in review until the required independent review is resolved.
