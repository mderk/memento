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

## Step 3: Organize Steps

Steps can live at the protocol root or be grouped into folders. Use a group when steps logically belong together or need their own scoped context (research, API notes, etc.). A group can contain even a single step if it has substantial context that isn't needed elsewhere.

Groups do not affect execution — all steps run sequentially in one worktree. Groups scope context: during execution, the agent loads only the current group's `_context/`, keeping the context window focused.

```
.protocols/0001-feature/
├── prd.md
├── plan.md
├── 01-setup.md                    # step at root
├── 02-infrastructure/             # group
│   ├── 01-database.md
│   ├── 02-api.md
│   └── _context/                  # group-scoped context
├── 03-auth/                       # group (1 step + heavy context)
│   ├── 01-oauth-integration.md
│   └── _context/
│       ├── provider-comparison.md
│       └── token-flow.md
├── 04-testing.md                  # step at root
└── _context/                      # protocol-wide context (optional)
```

## Step 4: Create plan.md

plan.md is the **single source of truth** for protocol status, progress, and step sequencing. The ADR section should be concise — link to prd.md for detailed requirements.

### Template

```markdown
# Protocol: [Feature Name]

**Status**: Draft | In Progress | Complete | Blocked
**Created**: YYYY-MM-DD
**PRD**: [./prd.md](./prd.md)

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

-   [ ] [Setup](./01-setup.md) — Xh est

### Infrastructure (02-infrastructure/)

-   [ ] [Database](./02-infrastructure/01-database.md) — Xh est
-   [ ] [API](./02-infrastructure/02-api.md) — Xh est

### Auth (03-auth/)

-   [ ] [OAuth Integration](./03-auth/01-oauth-integration.md) — Xh est

-   [ ] [Testing](./04-testing.md) — Xh est
```

Root-level steps and group headings mix freely. All steps execute sequentially in one worktree.

### Progress markers

| Marker | Meaning                         |
| ------ | ------------------------------- |
| `[ ]`  | Not started                     |
| `[~]`  | In progress                     |
| `[x]`  | Complete (committed + reviewed) |
| `[-]`  | Blocked                         |

After completion, add actual time: `— 3h est / 2.5h actual`

## Step 5: Create Step Files

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

Brief notes on relevant research or decisions. Keep per-step context here inline.
Shared context lives in `_context/` and is loaded automatically via `/load-context`.

## Findings

_Populated during execution. Record discoveries, decisions, and gotchas as they happen._

Optional tags: `[DECISION]`, `[GOTCHA]`, `[REUSE]`

## Memory Bank Impact

Expected documentation updates (review at protocol end):

-   [ ] What to update → which Memory Bank file
-   [ ] None expected
````

## Step 6: Save Context (if any)

If research was gathered during planning (library comparisons, API exploration, architecture sketches), save it in `_context/`. Don't create `_context/` if there's nothing to put there.

```bash
mkdir -p .protocols/0001-feature/_context
```

**What belongs in `_context/`:** research notes, API docs excerpts, architecture decisions, rejected approaches with rationale, benchmarks, stakeholder feedback. Also `findings.md` — runtime discoveries promoted from step files during execution (see [Process Protocol](./process-protocol.md)).

**Naming:** descriptive names (`architecture.md`, `research.md`, `findings.md`).

**Hierarchy:**

-   `protocol/_context/` — protocol-wide
-   `protocol/01-group/_context/` — group-specific

Per-step context belongs inline in the step file's `## Context` section — no separate files needed.

## Step 7: Review

Before proceeding to execution:

-   [ ] Source material saved as prd.md
-   [ ] ADR is concise (links to prd.md for details)
-   [ ] Steps properly sequenced in plan.md
-   [ ] Estimates provided for each step
-   [ ] Verification criteria defined in each step file
-   [ ] Research saved in `_context/` (if gathered)

Present the protocol summary to the user. **Do not start execution** — the user will run `/process-protocol` when ready.

## Examples

### Admin Dashboard

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

## Context

The application needs an admin interface for managing users and content.
Currently admins use direct database access. Full requirements in [prd.md](./prd.md).

## Decision

Build a dashboard within the existing application using the project's
UI framework. Server-side filtering with pagination for large datasets.

## Progress

-   [x] [Layout and Navigation](./01-layout-and-navigation.md) — 4h est / 3h actual
-   [x] [Data Tables](./02-data-tables.md) — 3h est / 4h actual
-   [~] [Filtering and Search](./03-filtering-and-search.md) — 3h est
-   [ ] [Export Functionality](./04-export-functionality.md) — 2h est
-   [ ] [Testing](./05-testing.md) — 3h est
```

### With folders: Notification System

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

-   [Process Protocol](./process-protocol.md) — Execute protocol steps
-   [Commit Message Rules](./commit-message-rules.md) — Commit conventions
