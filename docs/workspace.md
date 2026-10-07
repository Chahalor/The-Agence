# Workspace - The_Agence

## 1. Main agent roles

### Core roles

- architect
- coder
- tester
- reviewer
- perfs
- docs

### Optional / later

- release

| Role | Main mission | Must not do |
|---|---|---|
| **Architect** | Design architecture, interfaces, boundaries and constraints | Implement complete features unless an explicit prototype is requested |
| **Coder** | Implement a defined task | Redesign architecture or expand scope without approval |
| **Tester** | Verify behavior and write tests | Directly fix production/business code |
| **Reviewer** | Audit changes for bugs, inconsistencies, maintainability and scope compliance | Silently fix everything it finds |
| **Perfs** | Measure, profile and propose optimizations | Optimize without measurement or evidence |
| **Docs** | Maintain technical and user documentation | Change software behavior |
| **Release** | Prepare and validate releasable versions | Add unrelated features or bypass validation |

---

## 2. Role file template

Each role is defined in `.agence/roles/<role>.md`.

```markdown
# Role: <name>

## Mission

## Responsibilities

## Capabilities

### Allowed

### Forbidden

## Required context

## Workflow

## Outputs

## Stop conditions

## Handoffs
```

A role defines responsibilities and authority boundaries, not personality.

---

## 3. Repository architecture

```text
AGENTS.md

.agence/
├── INDEX.md
├── roles/
│   └── <role>.md
├── work/
│   └── T-xxx-<name>.md
└── knowledge/
    ├── decisions/
    │   └── D-xxx-<name>.md
    ├── notes/
    │   └── N-xxx-<name>.md
    └── reports/
        └── R-xxx-<name>.md
```

### Purpose

- `AGENTS.md`
  - Defines global behavior shared by all agents.
  - Defines role selection, context loading, communication rules, handoffs and escalation.

- `.agence/INDEX.md`
  - Provides a lightweight project-wide entry point.
  - Lists active work and important knowledge references.
  - Must not duplicate full document content.

- `.agence/roles/`
  - Contains role definitions.

- `.agence/work/`
  - Contains active and historical work items.
  - Each work item owns its local execution history and inter-agent communication.

- `.agence/knowledge/decisions/`
  - Contains durable project decisions.

- `.agence/knowledge/notes/`
  - Contains durable project knowledge that is informative but not normative.

- `.agence/knowledge/reports/`
  - Contains substantial analyses such as reviews, benchmark reports or investigation results.

---

## 4. Document IDs and filenames

Document IDs are short, human-readable and type-specific.

```text
T-xxx   Work
D-xxx   Decision
N-xxx   Note
R-xxx   Report
```

Examples:

```text
T-014-uuid-comparison.md
D-003-uuid-representation.md
N-006-uuid-parser-behavior.md
R-002-uuid-parser-benchmark.md
```

Rules:

- IDs are unique inside the project.
- References between Agence documents use their ID.
- Source code references use project-relative paths.
- A path may optionally include a line reference.

Examples:

```text
T-014
D-003
src/types/uuid.c
src/types/uuid.c:42
```

---

## 5. Common document metadata

All structured Agence documents use YAML frontmatter.

Common fields:

```yaml
---
schema: agence/<type>/v1
id: <ID>
title: <human-readable title>
status: <type-specific status>
tags: []
related: []
---
```

Rules:

- Frontmatter must remain machine-readable.
- Only indexable metadata belongs in frontmatter.
- Long descriptions, reasoning and results belong in Markdown sections.
- `related` contains Agence document IDs only.

---

# Work

## 6. Work lifecycle

Allowed work statuses:

```text
planned
active
blocked
review
completed
cancelled
```

Suggested meaning:

- `planned`
  - Work exists but no role is currently executing it.

- `active`
  - A role is actively responsible for progressing it.

- `blocked`
  - Progress cannot continue until a blocker is resolved.

- `review`
  - Implementation or work result exists and is waiting for validation/review.

- `completed`
  - Required work and validations are complete.

- `cancelled`
  - Work will not be completed.

`owner` identifies the role currently responsible for progressing the work.

A handoff changes the responsibility of the work:

```text
coder -> tester
```

The outgoing agent:

1. appends a `handoff` entry;
2. updates `owner` to the target role;
3. updates `Current state`;
4. updates `status` when appropriate.

A handoff does not automatically mean the work is complete.

---

## 7. Work format

```markdown
---
schema: agence/work/v1
id: T-014
title: UUID comparison
status: review
owner: tester
tags: [uuid, types]
related: [D-003]
---

# UUID comparison

## Goal

Implement deterministic UUID comparison.

## Constraints

- Comparison must not allocate.
- UUID representation must remain opaque to callers.

## Context

Relevant files:

- `include/types/uuid.h`
- `src/types/uuid.c`

Related knowledge:

- D-003

## Current state

Implementation completed. Behavioral validation is in progress.

## Activity

### decision · architect

UUID comparison operates on the canonical 16-byte representation.

Promoted to: D-003

### result · coder

Implemented `uuid_cmp()`.

Changed:

- `include/types/uuid.h`
- `src/types/uuid.c`

### finding · tester

Parser accepts non-canonical UUID representations.

Severity: warning

Refs:

- `src/types/uuid.c`

### handoff · tester → coder

Reject non-canonical UUID representations before comparison.
```

Required sections:

```text
Goal
Constraints
Context
Current state
Activity
```

`Current state` summarizes the current situation and must stay synchronized with reality.

`Activity` is an append-oriented execution history.

---

## 8. Work activity entries

Supported activity types:

```text
decision
finding
note
result
blocker
handoff
```

### `decision`

A choice made locally while executing the task.

```markdown
### decision · architect

Use byte-wise UUID comparison.

Reason: avoids conversion and allocation.
```

If the decision becomes durable project knowledge, promote it to a `D-xxx` document.

### `finding`

A discovered fact, problem, inconsistency or risk.

```markdown
### finding · reviewer

The parser accepts non-canonical UUID input.

Severity: warning

Refs:

- `src/types/uuid.c`
```

### `note`

Useful local information that does not represent a decision or problem.

```markdown
### note · coder

`uuid_cmp()` is also used by the sorting helper.
```

If the information becomes useful outside the task, promote it to an `N-xxx` document.

### `result`

Work performed or a concrete outcome.

```markdown
### result · tester

UUID comparison tests passed: 18/18.
```

### `blocker`

A condition preventing further progress.

```markdown
### blocker · coder

The requested implementation depends on an ownership rule that is not defined.

Requires: architect decision.
```

When unresolved, the work status should be `blocked`.

### `handoff`

Explicit transfer of responsibility to another role.

```markdown
### handoff · coder → tester

Validate comparison behavior and malformed UUID inputs.

Refs:

- `src/types/uuid.c`
- D-003
```

Agents must not silently change role. Work outside the current role is communicated through a finding, blocker or handoff.

---

# Knowledge

## 9. Knowledge promotion rule

Information starts local to a work item unless it has value beyond that task.

Promote information when it becomes durable or project-wide.

```text
local task information
    -> remains in T-xxx

durable project decision
    -> D-xxx

durable project knowledge
    -> N-xxx

substantial analysis
    -> R-xxx
```

Do not duplicate the same information in several documents.

The work item should reference the promoted document.

Example:

```markdown
### decision · architect

UUID values use a canonical 16-byte representation.

Promoted to: D-003
```

---

# Decisions

## 10. Decision format

Decision statuses:

```text
proposed
accepted
rejected
deprecated
superseded
```

```markdown
---
schema: agence/decision/v1
id: D-003
title: UUID canonical representation
status: accepted
tags: [uuid, types]
related: [T-014]
---

# UUID canonical representation

## Decision

UUID values are stored internally as exactly 16 canonical bytes.

## Rationale

This gives UUID values a unique internal representation and allows
comparison without string conversion or allocation.

## Consequences

- Comparison operates directly on the byte representation.
- Parsers must normalize or reject invalid representations.
- String form is presentation only.

## Alternatives

### Store textual UUIDs

Rejected because comparison and storage would be unnecessarily expensive.

## References

- T-014
- `include/types/uuid.h`
```

Required sections:

```text
Decision
Rationale
Consequences
References
```

Optional:

```text
Alternatives
```

When superseded, the old decision remains available for history and references the replacement.

Example:

```yaml
status: superseded
related: [D-017]
```

---

# Notes

## 11. Note format

Notes contain durable information that is useful to future work but does not impose a project decision.

Note statuses:

```text
draft
current
outdated
superseded
```

```markdown
---
schema: agence/note/v1
id: N-006
title: UUID parser behavior
status: current
tags: [uuid, parsing]
related: [T-014, D-003]
---

# UUID parser behavior

## Summary

The current UUID parser accepts uppercase and lowercase hexadecimal
characters and validates separator placement.

It does not currently enforce canonical textual representation.

## Details

`uuid_parse()` converts the textual UUID into its binary representation.

The parser validates:

- hexadecimal characters;
- separator positions;
- total input length.

Canonical textual normalization is not enforced before conversion.

## Implications

Code that requires canonical textual UUIDs must not assume that
successful parsing implies canonical input.

This may affect validation APIs and serialized representations.

## References

- `src/types/uuid.c`
- `include/types/uuid.h`
- T-014
- D-003
```

Required:

```text
Summary
```

Optional:

```text
Details
Implications
References
```

A Note means:

```text
"This is useful information about the project."
```

A Decision means:

```text
"This is the behavior / rule selected by the project."
```

---

# Reports

## 12. Report format

Reports contain substantial analyses.

Examples:

- code review;
- performance analysis;
- benchmark;
- investigation;
- test campaign;
- security analysis.

Report statuses:

```text
draft
final
obsolete
```

```markdown
---
schema: agence/report/v1
id: R-002
title: UUID parser benchmark
status: final
tags: [uuid, performance]
related: [T-014]
---

# UUID parser benchmark

## Objective

Measure the cost of UUID parsing.

## Method

...

## Results

...

## Findings

...

## Recommendations

...

## References

...
```

A short result stays in the related `T-xxx`.

A separate `R-xxx` is created only when the analysis is substantial enough to justify an independent document.

A report describes analysis and evidence.

A decision describes what the project has selected.

---

# Index

## 13. INDEX.md format

`INDEX.md` is the lightweight project-wide entry point.

It should be cheap for an agent to read.

Example:

```markdown
# The Agence Index

## Active work

| ID | Work | Status | Owner |
|---|---|---|---|
| T-014 | UUID comparison | review | tester |
| T-015 | Arena allocator | active | coder |

## Decisions

- D-003 — UUID canonical representation
- D-004 — Settings publication model

## Notes

- N-006 — UUID parser behavior

## Reports

- R-002 — UUID parser benchmark
```

Rules:

- Keep the index concise.
- Do not duplicate document bodies.
- Prefer references over summaries.
- Completed work may be omitted from the main active-work view.
- The index exists to discover context, not replace it.

---

# Capabilities & Permissions

## 14. Permission model

Permissions describe actions that can eventually be technically enforced.

A role's responsibilities and a role's permissions are separate concepts.

```text
role
    -> what the agent is responsible for

permission
    -> what the agent is technically allowed to do
```

### Default policy

Permissions are **deny by default**.

Anything not explicitly allowed is considered forbidden.

### Scoped permissions

Permissions should be scoped whenever possible.

Example:

```yaml
fs.read:
  - "**"

fs.write:
  - "src/**"
  - "include/**"

exec.run:
  - make
  - cmake
  - ctest

git.read: true
git.commit: false

network.outbound: false
```

The exact enforcement mechanism may initially be declarative.

The permission vocabulary should still be designed so that a future sandbox or tool layer can enforce it directly.

---

## 15. Permission vocabulary

```text
filesystem
├── fs.read
├── fs.create
├── fs.write
├── fs.delete
└── fs.move

execution
├── exec.run
└── exec.shell

git
├── git.read
├── git.stage
├── git.commit
├── git.branch
├── git.checkout
├── git.merge
├── git.rebase
├── git.fetch
├── git.pull
├── git.push
├── git.tag
└── git.push_tag

network
├── network.outbound
└── network.listen

dependencies
├── deps.install
├── deps.update
└── deps.remove

environment
├── environment.read
└── environment.write

secrets
├── secrets.read
└── secrets.write

process/system
├── process.spawn
├── process.kill
├── service.read
├── service.control
├── container.run
├── container.build
├── system.read
├── system.write
└── privilege.sudo

agence
├── agence.task.read
├── agence.task.write
├── agence.knowledge.read
├── agence.knowledge.write
├── agence.role.read
├── agence.role.write
├── agence.index.read
└── agence.index.write
```

### Important restrictions

An agent should not receive permission to modify its own role definition unless explicitly requested.

Sensitive permissions should remain exceptional:

```text
secrets.read
secrets.write
system.write
privilege.sudo
git.push
git.push_tag
agence.role.write
```

---

# Agent execution model

## 16. Work cycle

```text
load global rules
   ↓
load role
   ↓
load task
   ↓
load referenced knowledge
   ↓
execute role-specific work
   ↓
update task
   ↓
promote durable information when needed
   ↓
handoff / complete / blocked
```

An agent should load only the context relevant to its task.

It should not blindly load all files under `.agence/`.

---

## 17. Global AGENTS.md contract

`AGENTS.md` must define the rules shared by every role.

At minimum:

### Role selection

A chat operates under one explicit role.

Example:

```text
ROLE: coder
TASK: T-014
```

The agent must load:

1. `AGENTS.md`
2. `.agence/roles/<role>.md`
3. `.agence/INDEX.md`
4. the requested `T-xxx`
5. knowledge referenced by the work item when relevant

### Role boundaries

- An agent does not silently change role.
- An agent does not perform work explicitly owned by another role unless authorized.
- Out-of-scope work is reported through `finding`, `blocker` or `handoff`.

### Communication

Agents communicate through the relevant `T-xxx` work file.

Agents should not require the user to rewrite reports or manually prepare prompts for another role.

### Documentation

- Keep frontmatter valid.
- Keep `Current state` synchronized.
- Treat `Activity` as append-oriented history.
- Use project-relative paths.
- Reference Agence documents by ID.
- Avoid duplicating information available through a reference.
- Promote durable knowledge instead of copying it between tasks.

### Reasoning hygiene

Record:

- decisions;
- useful rationale;
- findings;
- results;
- blockers;
- handoffs.

Do not record:

- hidden chain-of-thought;
- conversational filler;
- speculative internal monologue;
- irrelevant implementation narration.

### Permissions

- Deny by default.
- Respect role permissions and scopes.
- Lack of permission is a blocker, not an invitation to bypass the model.
- Agents may not grant themselves additional permissions.

### Completion

Before finishing work, an agent must:

1. update the work item's `Current state`;
2. append relevant activity entries;
3. promote durable knowledge when necessary;
4. either:
   - complete the work;
   - hand it off;
   - mark it blocked.

---

## 18. Design principles

The Agence V0 should remain:

```text
role-based
explicit
file-based
human-readable
machine-indexable
lightweight
progressively enforceable
```

Avoid adding new persistent object types unless an actual workflow requires them.

The initial persistent document types are intentionally limited to:

```text
T-xxx  Work
D-xxx  Decision
N-xxx  Note
R-xxx  Report
```

The initial communication primitives are intentionally limited to:

```text
decision
finding
note
result
blocker
handoff
```
