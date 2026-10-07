---
schema: agence/work/v1
id: T-001
title: Initialize scripts tA workspace
status: completed
owner: docs
tags: [scripts, setup]
related: [N-001]
---

# Initialize scripts tA workspace

## Goal

Prepare `scripts/` for agents to work using The Agence.

## Constraints

- Reuse the existing global rules and six core role templates.
- Keep setup scoped to `scripts/`.
- The user clarified that this mission initializes agent files only.
- Preserve the Python CLI specification; implementation is outside this mission.

## Context

- `docs/workspace.md`
- `Workspaces/AGENTS.md`
- `Workspaces/docs.md`
- `scripts/agence/README.md`
- N-001

## Current state

Scripts workspace initialized and checked. No active work remains in this mission.
The Python helper remains a specification awaiting a future implementation mission.

## Activity

### note · docs

2026-10-06: The user requested tA agent files in `scripts/`, rather than
implementation of the Python helper.

### result · docs

Copied global rules and six core roles. Added local scope guidance, a bootstrap
index and N-001. Created work and all three knowledge directories.

### result · docs

Validated required directories, exact role-template copies, global-template
preservation, document filenames, YAML frontmatter, required sections, related
IDs, source references and index links. All checks passed.
