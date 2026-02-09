# Create Protocol Workflow

## Goal

Generate a structured protocol from a PRD or task description for complex features requiring multi-phase implementation.

## When to Use

-   Complex features requiring multiple implementation phases
-   Major refactorings needing architectural context
-   Cross-cutting changes affecting multiple subsystems
-   Long-running work needing progress tracking across sessions

Protocol language: English, unless specified otherwise explicitly.

## Step 1: Create Protocol Directory

```bash
# Determine next number: list existing protocols, take max + 1
ls .protocols/
# If empty or doesn't exist → 0001
# If 0001-*, 0002-* exist → 0003

mkdir -p .protocols/NNNN-feature-name
```

## Step 2: Save Source Material as prd.md

Save the source requirements — PRD, task description, Claude Code plan, or user brief — as `prd.md` in the protocol root. This keeps the ADR in plan.md concise while preserving full requirements.

-   If a formal PRD exists: copy it (or link if already version-controlled in the same repo)
-   If the source is a chat message, plan, or verbal brief: process into structured requirements
-   If the source is an external document: extract and save relevant content

**prd.md is a snapshot** — it captures requirements at creation time. Later changes go into plan.md, not prd.md.

**Template** (when processing from unstructured source):

```markdown
# [Feature Name] — Requirements

## Problem Statement

What needs to be solved.

## Requirements

-   Functional requirements
-   Non-functional requirements (performance, security, etc.)

## Constraints

-   Technical constraints
-   Timeline, resources

## Acceptance Criteria

-   How to verify the feature is complete

## Source

Original source: [link or description of origin]
Captured: YYYY-MM-DD
```

## Step 3: Choose Structure — Flat or Folders

Most protocols are flat. Use folders only when there's a reason.

| Signal             | → Flat                      | → Folders                                           |
| ------------------ | --------------------------- | --------------------------------------------------- |
| Total steps        | ≤5                          | 6+                                                  |
| Step groupings     | No natural clusters         | Clear logical clusters                              |
| Group independence | All steps serve one feature | Groups are self-contained, deployable independently |
| Context materials  | Few, shared                 | Per-group research needed                           |

**Rule of thumb:** if all steps form a simple numbered list — flat. If you want to group them under headings — folders.

Maximum nesting depth: 2 levels (protocol → group → steps). If a group needs sub-groups, split into multiple protocols.

**Flat:**

```
.protocols/0001-feature/
├── prd.md
├── plan.md
├── 01-step-name.md
├── 02-step-name.md
└── _context/           # optional
```

**With folders:**

```
.protocols/0001-feature/
├── prd.md
├── plan.md
├── 01-group-name/
│   ├── 01-step.md
│   └── 02-step.md
├── 02-group-name/
│   ├── 01-step.md
│   └── 02-step.md
└── _context/           # optional
```

If using folders, create group directories now (protocol directory was created in step 1):

```bash
mkdir -p .protocols/0001-feature/01-group-name
mkdir -p .protocols/0001-feature/02-group-name
```

## Step 4: Choose Branching Strategy

| Strategy                 | When to Use                                             | Example                          |
| ------------------------ | ------------------------------------------------------- | -------------------------------- |
| `per-protocol` (default) | Steps are parts of one feature                          | Building a dashboard             |
| `per-step`               | Each step is independent and self-contained             | Fixing unrelated tech debt items |
| `per-group`              | Clusters of related steps, but clusters are independent | Auth system + notifications      |

**Decision criteria:**

-   All steps needed together for the feature to work? → `per-protocol`
-   Can each step be deployed to production on its own? → `per-step`
-   Natural groupings of dependent steps? → `per-group`

**If unsure, use `per-protocol`.** It's the default — if omitted from plan.md, `per-protocol` is assumed.

Note: `per-group` **requires** folder structure (step 3). If you chose flat, pick `per-protocol` or `per-step`.

## Step 5: Create plan.md

plan.md is the **single source of truth** for protocol status, progress, and step sequencing. The ADR section should be concise — link to prd.md for detailed requirements.

Use the template matching your structure choice from step 3.

### Template: Flat

```markdown
# Protocol: [Feature Name]

**Status**: Draft | In Progress | Review | Complete | Blocked
**Created**: YYYY-MM-DD
**PRD**: [./prd.md](./prd.md)
**Branching**: per-protocol

## Context

Brief summary of the problem (1-3 sentences). Full requirements in [prd.md](./prd.md).

## Decision

What approach are we taking?

-   High-level solution
-   Key architectural choices
-   Trade-offs considered
-   **Testability**: How will this be tested? (unit/integration/e2e)

## Rationale

Why this approach over alternatives?

-   Alternative 1: Pros/Cons
-   Alternative 2: Pros/Cons
-   Chosen approach: Why it's best for our context

## Consequences

### Positive

-   Benefit 1
-   Benefit 2

### Negative

-   Drawback 1 (and mitigation)
-   Drawback 2 (and mitigation)

## Progress

-   [ ] [Step 1 Name](./01-step-name.md) — Xh est
-   [ ] [Step 2 Name](./02-step-name.md) — Xh est
-   [ ] [Step 3 Name](./03-step-name.md) — Xh est
```

### Template: With groups

Same ADR sections as above, but Progress uses group headings:

```markdown
## Progress

### Group 1: [Group Name] (01-group-name/)

-   [ ] [Step Name](./01-group-name/01-step.md) — Xh est
-   [ ] [Step Name](./01-group-name/02-step.md) — Xh est

### Group 2: [Group Name] (02-group-name/)

-   [ ] [Step Name](./02-group-name/01-step.md) — Xh est
-   [ ] [Step Name](./02-group-name/02-step.md) — Xh est
```

### Progress markers

| Marker | Meaning                                      |
| ------ | -------------------------------------------- |
| `[ ]`  | Not started                                  |
| `[~]`  | In progress                                  |
| `[x]`  | Complete (subtasks done, tests pass)         |
| `[✓]`  | Approved (code review passed, per-step only) |
| `[M]`  | Merged                                       |
| `[-]`  | Blocked                                      |

After completion, add actual time: `— 3h est / 2.5h actual`

## Step 6: Create Step Files

Step files are **focused work descriptions**. They do NOT contain status, estimates, dependencies, or next step links — all of that lives in plan.md.

````markdown
# [Step Name]

## Objective

What this step accomplishes and why.

## Tasks

-   [ ] Task description
-   [ ] Task description
-   [ ] Task description

## Implementation Notes

Key considerations:

-   Pattern to follow: reference existing code
-   Key files to modify: list paths
-   How to test: describe approach

## Verification

```bash
# Commands to verify step is working
```

## Context

Brief notes on relevant research or decisions.

-   [Full comparison details](./_context/step-03-research.md) ← only if bulky

## Findings

_Populated during execution. Record discoveries, decisions, and gotchas as they happen._

Optional tags: `[DECISION]`, `[GOTCHA]`, `[REUSE]`

## Memory Bank Impact

Expected documentation updates (review at protocol end):

-   [ ] What to update → which Memory Bank file
-   [ ] None expected
````

## Step 7: Save Context (if any)

If research was gathered during planning (library comparisons, API exploration, architecture sketches), save it in `_context/`. Don't create `_context/` if there's nothing to put there.

```bash
mkdir -p .protocols/0001-feature/_context
```

**What belongs in `_context/`:** research notes, API docs excerpts, architecture decisions, rejected approaches with rationale, benchmarks, stakeholder feedback. Also `findings.md` — runtime discoveries promoted from step files during execution (see [Process Protocol](./process-protocol.md) Step 4).

**Naming:** shared context uses descriptive names (`architecture.md`, `research.md`, `findings.md`). Step-specific bulky materials use step prefix (`step-03-auth-research.md`).

**Hierarchy** (folder structure only):

-   `protocol/_context/` — protocol-wide
-   `protocol/01-group/_context/` — group-specific

Small per-step context goes directly in the step file's `## Context` section — no separate file needed.

## Step 8: Review

Before proceeding to execution:

-   [ ] Source material saved as prd.md
-   [ ] ADR is concise (links to prd.md for details)
-   [ ] Steps properly sequenced in plan.md
-   [ ] Estimates provided for each step
-   [ ] Branching strategy selected
-   [ ] Verification criteria defined in each step file
-   [ ] Folder structure matches strategy (groups = folders for per-group)
-   [ ] Research saved in `_context/` (if gathered)

Present the protocol summary to the user. **Do not start execution** — the user will run `/process-protocol` when ready.

## Examples

### Flat: Admin Dashboard (per-protocol)

```
.protocols/0001-admin-dashboard/
├── prd.md
├── plan.md
├── 01-layout-and-navigation.md
├── 02-data-tables.md
├── 03-filtering-and-search.md
├── 04-export-functionality.md
└── 05-testing.md
```

**plan.md excerpt:**

```markdown
# Protocol: Admin Dashboard

**Status**: In Progress
**Created**: 2025-06-15
**PRD**: [./prd.md](./prd.md)
**Branching**: per-protocol

## Context

The application needs an admin interface for managing users and content.
Currently admins use direct database access. Full requirements in [prd.md](./prd.md).

## Decision

Build a dashboard within the existing application using the project's
UI framework. Server-side filtering with pagination for large datasets.

## Progress

-   [M] [Layout and Navigation](./01-layout-and-navigation.md) — 4h est / 3h actual
-   [M] [Data Tables](./02-data-tables.md) — 3h est / 4h actual
-   [~] [Filtering and Search](./03-filtering-and-search.md) — 3h est
-   [ ] [Export Functionality](./04-export-functionality.md) — 2h est
-   [ ] [Testing](./05-testing.md) — 3h est
```

**Step file excerpt (03-filtering-and-search.md):**

````markdown
# Filtering and Search

## Objective

Add server-side filtering, search, and pagination to admin data tables
so admins can efficiently find specific records.

## Tasks

-   [ ] Implement filter query builder
-   [ ] Add search input with debounce
-   [ ] Connect filters to data table component
-   [ ] Add URL state sync for shareable filter views

## Implementation Notes

-   Follow existing data table patterns in the codebase
-   Filters should be composable (AND logic)
-   URL params: `?filter[status]=active&search=query&page=2`

## Verification

```bash
npm test -- --filter=admin
npm run e2e -- --filter=admin-filters
```

## Context

Server-side filtering chosen over client-side for large datasets.
URL state sync allows sharing filtered views between admins.

## Findings

_Populated during execution._

## Memory Bank Impact

-   [ ] Pattern: server-side filtering approach → patterns/api-design.md
````

### With folders: Notification System (per-group)

```
.protocols/0002-notification-system/
├── prd.md
├── plan.md
├── 01-infrastructure/
│   ├── 01-message-queue.md
│   ├── 02-delivery-service.md
│   └── _context/
│       └── queue-comparison.md
├── 02-channels/
│   ├── 01-email-channel.md
│   ├── 02-push-channel.md
│   └── _context/
│       └── provider-api-notes.md
└── _context/
    └── architecture.md
```

## Related Documentation

-   [Process Protocol](./process-protocol.md) - Execute protocol steps
-   [Git Worktree Workflow](./git-worktree-workflow.md) - Branch isolation
