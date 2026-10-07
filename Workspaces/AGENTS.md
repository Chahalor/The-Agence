# The Agence

This repository uses **The Agence**, a lightweight role-based coordination system for AI agents.

This file is the global entry point for every agent working in the repository.

Its purpose is to let an agent quickly understand:

- how the system is organized;
- what role it is currently operating under;
- where project work and shared knowledge are stored;
- how to communicate with other agents;
- how role boundaries and permissions work;
- how to leave the project in a state another agent can continue from.

The Agence is a coordination system, not an autonomous orchestrator.
The user remains the highest project-level authority.

---

# 1. Core principles

The Agence follows these principles:

```text
role-based
explicit
file-based
human-readable
machine-indexable
lightweight
progressively enforceable
```

Agents must prefer the smallest amount of process necessary to complete the current mission.

Do not invent new workflow layers, document types, roles, metadata fields or coordination mechanisms unless they solve an actual project need.

---

# 2. Repository layout

The coordination data lives under `.agence/`.

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

Purpose:

```text
AGENTS.md
    global rules for every agent

.agence/INDEX.md
    lightweight map of active work and shared knowledge

.agence/roles/
    role definitions

.agence/work/
    tracked project work and inter-agent communication

.agence/knowledge/decisions/
    durable project decisions

.agence/knowledge/notes/
    durable useful project knowledge

.agence/knowledge/reports/
    substantial analyses and investigation results
```

Do not blindly load every file under `.agence/`.
Load only the context needed for the current mission.

---

# 3. Starting a mission

A normal role-based mission may be started with:

```text
ROLE: coder
TASK: T-014
```

`ROLE` selects the default role definition.

`TASK` points to a tracked work item.

Both fields are useful conventions, not magic syntax.

The user's actual instruction remains authoritative.

---

# 4. Context loading

For a tracked role-based task, load context in this order:

1. `AGENTS.md`
2. `.agence/roles/<role>.md`
3. `.agence/INDEX.md`
4. the requested `.agence/work/T-xxx-*.md`
5. knowledge explicitly referenced by that work item
6. project files relevant to the requested work

Load additional knowledge only when it is relevant.

Do not consume the entire project history merely because it exists.

If no tracked task is provided, use the user's request as the mission context and load only the project information required to execute it.

---

# 5. Instruction precedence

When instructions conflict, use this order:

```text
platform / environment / tool restrictions
        ↓
explicit user instruction for the current mission
        ↓
AGENTS.md
        ↓
selected role definition
        ↓
tracked work item
        ↓
referenced project knowledge
```

Project decisions and notes remain important context, but an explicit user instruction may intentionally override an existing project choice for the current mission.

When such an override materially changes the project, record the resulting decision or consequence in the appropriate project documents if permitted.

Never treat a role definition as higher authority than an explicit user instruction.

---

# 6. Roles

A role defines the agent's **default responsibility boundary**.

Role files live in:

```text
.agence/roles/<role>.md
```

A role definition describes:

```text
Mission
Responsibilities
Capabilities
Required context
Workflow
Outputs
Stop conditions
Handoffs
```

A role is not a personality.

A role exists to answer:

```text
What am I normally responsible for?
What should I normally avoid doing?
What context do I need?
What result am I expected to leave behind?
When should another role take over?
```

---

# 7. Role boundaries are defaults, not cages

Role boundaries apply by default.

An agent must not silently expand its scope merely because adjacent work appears useful.

For example, a `tester` should normally report a production-code bug rather than silently becoming the `coder`.

However, an **explicit user instruction may authorize work outside the selected role**.

Example:

```text
ROLE: tester

Test the parser, and if the failure is trivial, fix it directly.
```

The tester may perform that explicitly authorized fix.

Another example:

```text
ROLE: coder

For this task, also make the required API design decision and document it.
```

The coder may perform that architecture/documentation work because the user explicitly assigned it.

Rules for explicit role overrides:

- The override applies only to the requested action and its necessary scope.
- It does not permanently change the role.
- It does not grant unrelated authority.
- It does not imply permission to perform every adjacent task.
- It does not override platform, sandbox, tool, security or other hard restrictions.
- It does not allow an agent to grant itself additional technical permissions.
- The agent should continue following the selected role for everything not covered by the explicit override.

Do not refuse a user-requested action solely because it normally belongs to another role.

---

# 8. Direct missions without a role

The role system must not prevent useful work.

If the user explicitly assigns a mission without selecting a role, the agent may execute it as a **direct mission**.

In direct-mission mode:

- the user's requested scope defines the responsibility boundary;
- existing role files may be consulted for useful workflow guidance;
- the agent does not need to pretend to hold a role;
- role-specific prohibitions do not block the explicitly assigned work;
- technical permissions and global project rules still apply.

Do not create a fictional role merely to fit an unusual task.

---

# 9. Roles versus permissions

Roles and permissions are separate concepts.

```text
role
    what the agent is responsible for

permission
    what the agent is technically allowed to do
```

A role boundary is normally a coordination rule.

A permission boundary is a capability restriction.

Example:

```text
The tester role normally does not edit production code.
```

This is a role boundary and may be overridden by an explicit user mission.

Example:

```text
fs.write does not allow src/**
```

This is a permission boundary and cannot be bypassed merely because the role or user request would benefit from it.

If a required technical capability is unavailable:

1. do not bypass it;
2. complete everything still possible;
3. record the limitation when working in a tracked task;
4. leave a blocker or handoff if the missing capability prevents completion.

---

# 10. Permission policy

Permissions are deny-by-default.

Anything not explicitly allowed should be treated as unavailable once permission enforcement is active.

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

Agents must never grant themselves additional permissions.

An explicit user mission may broaden responsibility, but actual capability escalation must occur through whatever permission mechanism the environment provides.

Sensitive capabilities deserve particular caution:

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

# 11. Permission vocabulary

The current permission vocabulary is:

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

An agent must not modify its own role definition unless explicitly instructed and technically permitted to do so.

---

# 12. Tracked work

Tracked work lives in:

```text
.agence/work/T-xxx-<name>.md
```

Work items are the main coordination point between agents.

A work file contains:

```text
Goal
Constraints
Context
Current state
Activity
```

The frontmatter contains the current status and owner.

Supported statuses:

```text
planned
active
blocked
review
completed
cancelled
```

Meaning:

```text
planned
    work exists but is not currently being executed

active
    a role is actively progressing the work

blocked
    progress cannot continue until a blocker is resolved

review
    produced work is waiting for validation or review

completed
    required work and validation are complete

cancelled
    the work will not be completed
```

`owner` identifies the role currently responsible for progressing the tracked work.

---

# 13. Work activity

Agents communicate through the `Activity` section of the relevant work item.

Supported activity primitives:

```text
decision
finding
note
result
blocker
handoff
```

Use only the primitive that best describes the information.

## decision

A choice made while executing the task.

```markdown
### decision · architect

Use byte-wise UUID comparison.

Reason: avoids conversion and allocation.
```

If the choice becomes durable project policy, promote it to a Decision document.

## finding

A discovered fact, problem, inconsistency or risk.

```markdown
### finding · reviewer

The parser accepts non-canonical UUID input.

Severity: warning

Refs:

- `src/types/uuid.c`
```

## note

Useful task-local information that is neither a decision nor a problem.

```markdown
### note · coder

`uuid_cmp()` is also used by the sorting helper.
```

If it becomes useful outside the task, promote it to a Note document.

## result

Concrete work performed or an observed outcome.

```markdown
### result · tester

UUID comparison tests passed: 18/18.
```

## blocker

A condition that prevents further progress.

```markdown
### blocker · coder

The implementation depends on an undefined ownership rule.

Requires: architect decision.
```

## handoff

An explicit transfer of responsibility.

```markdown
### handoff · coder → tester

Validate comparison behavior and malformed UUID inputs.

Refs:

- `src/types/uuid.c`
- D-003
```

---

# 14. Handoffs

Use a handoff when another role should continue the tracked work.

The outgoing agent should, when permitted:

1. append a `handoff` activity entry;
2. update `owner` to the target role;
3. update `Current state`;
4. update `status` when appropriate.

A handoff transfers responsibility.

It does not mean the task is complete.

Do not ask the user to manually rewrite a report or manufacture a prompt for the next agent.

The work file should contain enough durable context for the next agent to continue directly.

---

# 15. Shared knowledge

Project-wide knowledge lives under:

```text
.agence/knowledge/
```

Persistent document types are intentionally limited to:

```text
D-xxx  Decision
N-xxx  Note
R-xxx  Report
```

Use them as follows:

```text
Decision
    a durable project choice or rule

Note
    durable useful information that does not impose a rule

Report
    substantial analysis, investigation or measured result
```

Information starts local to a work item unless it has value beyond that work item.

Promote information when it becomes durable:

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

Do not duplicate the same content across multiple documents.

Reference the promoted document instead.

---

# 16. Document references

Use short project-local IDs:

```text
T-014
D-003
N-006
R-002
```

Use project-relative paths for repository files:

```text
src/types/uuid.c
include/types/uuid.h
```

A line may be referenced when useful:

```text
src/types/uuid.c:42
```

Do not invent URI schemes or opaque identifiers when the existing ID or path is sufficient.

---

# 17. INDEX.md

`.agence/INDEX.md` is the lightweight map of The Agence state.

It exists to help agents discover relevant context.

It may contain:

```text
active work
important/current decisions
useful notes
reports
```

Keep it concise.

Do not copy full document bodies into the index.

Prefer references.

When an agent creates, completes, supersedes or materially changes a tracked document, update the index if:

- the change belongs in the index;
- the agent has permission to modify it.

If the index should be updated but the agent cannot modify it, record that fact in the relevant work item rather than bypassing permissions.

---

# 18. Documentation rules

When modifying Agence documents:

- keep YAML frontmatter valid;
- use only defined metadata fields unless a new field is genuinely required;
- keep `Current state` synchronized with reality;
- treat `Activity` as append-oriented history;
- use project-relative paths;
- reference Agence documents by ID;
- prefer references over duplicated content;
- promote durable knowledge instead of copying it between work items;
- keep entries concise and factual;
- preserve useful historical information.

Do not store hidden chain-of-thought or speculative internal monologue.

Record only useful durable information such as:

```text
decisions
reasons needed to understand decisions
findings
results
blockers
handoffs
```

Conversational filler and step-by-step internal reasoning do not belong in project memory.

---

# 19. Normal work cycle

For a tracked role-based mission:

```text
load global rules
   ↓
load role
   ↓
load task
   ↓
load referenced knowledge
   ↓
inspect relevant project state
   ↓
execute role-specific work
   ↓
update task
   ↓
promote durable information when needed
   ↓
handoff / complete / blocked
```

This is a default workflow, not a ritual.

Skip steps that are irrelevant to the mission.

Do not perform work merely to satisfy the workflow.

---

# 20. Scope and escalation

During normal role-based work:

- stay within the requested mission;
- do not expand scope merely because adjacent improvements are possible;
- report important out-of-scope findings;
- use a handoff when another role should continue the work;
- use a blocker when progress genuinely cannot continue.

Do not use role boundaries as an excuse to avoid explicitly assigned work.

Do not use explicit assignment as an excuse to expand beyond what was requested.

The intended behavior is:

```text
default:
    respect role boundaries

explicit user override:
    perform the requested cross-role action

technical restriction:
    respect the restriction
```

---

# 21. Completion

Before ending tracked work, the agent should leave the project in a state another agent can understand.

When permitted and relevant:

1. update `Current state`;
2. append meaningful activity entries;
3. update status and owner;
4. promote durable knowledge;
5. update `INDEX.md` when required;
6. either:
   - mark the work complete;
   - hand it off;
   - mark it blocked.

Do not claim completion when required work is still unresolved.

---

# 22. Minimalism rule

The Agence is intentionally small.

The initial persistent document types are:

```text
T-xxx  Work
D-xxx  Decision
N-xxx  Note
R-xxx  Report
```

The initial communication primitives are:

```text
decision
finding
note
result
blocker
handoff
```

Do not add sessions, event stores, mailboxes, queues, agent identities, orchestration layers or new persistent object types merely because they might be useful someday.

Add structure when an actual workflow proves that the current model is insufficient.
