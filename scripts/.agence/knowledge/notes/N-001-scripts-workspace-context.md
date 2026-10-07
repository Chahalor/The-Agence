---
schema: agence/note/v1
id: N-001
title: Scripts workspace context
status: current
tags: [scripts, setup]
related: [T-001]
---

# Scripts workspace context

## Summary

The `scripts/` directory has its own tA workspace at `scripts/.agence/`, with
local global rules in `scripts/AGENTS.md` and six core roles copied from
`Workspaces/`. The workspace tracks script-related missions and knowledge.

## Details

- tA is a lightweight file-based coordination system with explicit roles, work
  ownership, activity entries and handoffs.
- `docs/workspace.md` describes the current document architecture and schemas.
- `Workspaces/AGENTS.md` and the six role files in `Workspaces/` are reusable templates.
- `dev/TODO.md` contains earlier design ideas; its historical .agents/ directory layout differs
  from the current coordination-directory specification in `docs/workspace.md`.
- `scripts/agence/README.md` specifies a Python helper with `setup`, `check`
  (`file`, `dir`, `refs`, `all`), `new` (`work`, `decision`, `note`, `report`),
  `index`, and `status` commands. No implementation exists at setup time.

## Implications

Load `scripts/AGENTS.md`, the selected local role, and the local index first.
Then load the assigned task and relevant referenced knowledge. Work files carry
local execution history; promote durable decisions, notes or substantial reports
only when useful beyond that task. References to source files are relative to
The_Agence repository root. Agence IDs are local to this workspace.

## References

- `docs/workspace.md`
- `Workspaces/AGENTS.md`
- `scripts/AGENTS.md`
- `scripts/agence/README.md`
- T-001
