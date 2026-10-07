---
schema: agence/decision/v1
id: D-001
title: Python CLI architecture
status: accepted
tags: [cli, architecture, python]
related: [T-002]
---

# Python CLI architecture

## Decision

Implement the README command surface as a small installable Python package in
`scripts/agence/`, exposing the console command `ta` and `python -m agence`.
Use Python 3.10 or newer, standard-library `argparse`, and PyYAML for safe YAML
loading and serialization. Declare PyYAML as a runtime dependency; do not write
a partial YAML parser. These are architect-selected implementation defaults,
not additional requirements stated by the README.

Markdown documents remain the source of truth. Do not introduce a database,
agent runtime, network service, permission enforcer or persistent ID counter.
The tool manages coordination files; role capabilities remain declarative.

Use one shared document catalog for checks, ID resolution, index rendering and
status. Parse and validate once per invocation. Keep command dispatch separate
from document rules, workspace discovery and filesystem operations.

`scripts/.agence/INDEX.md` is derived output. `setup` and `new` regenerate it, and `index`
regenerates it after external document edits. Checks and status read current
source documents rather than trusting an existing index. Once implemented,
agent instructions must direct index changes through the generator.

The implementation sequence and detailed command contracts live in T-002.

## Rationale

The requested commands all operate on the same small set of files and schemas.
A shared catalog prevents inconsistent validation and duplicated traversal.
Safe YAML support preserves the specified human-readable metadata format.
A console entry point makes the README's `ta status T-014` example practical.

## Consequences

- Package template resources so setup also works outside this repository.
- Stage resource copies from `Workspaces/`, the canonical rules and roles;
  document synchronization and check copies against their source during release
  validation. The scripts workspace's local agent files are not setup templates.
- Support UTF-8 documents, deterministic output and read-only check/status paths.
- New document IDs are allocated from existing files, without a counter file.
- Preserve existing instructions and role files during repeated setup.
- Index generation owns only `scripts/.agence/INDEX.md`; it must not rewrite task activity.
- Index ownership requires a narrow instruction update during implementation,
  including the bootstrap exception in `scripts/AGENTS.md`. Do not alter roles.

## Alternatives

A single large script would initially be quick but would couple parsing,
validation, formatting and mutations. A framework, database or orchestration
layer would exceed the file-helper scope. A custom YAML subset would reject
valid metadata or interpret it inconsistently.

## References

- T-002
- `scripts/agence/README.md`
- `docs/workspace.md`
- `Workspaces/AGENTS.md`
- `scripts/AGENTS.md`
