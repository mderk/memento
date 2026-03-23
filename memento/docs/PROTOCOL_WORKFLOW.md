# Protocol Workflow

The Protocol system is a structured pipeline for complex features that span multiple steps, require progress tracking across sessions, and benefit from isolated branches.

## When to Use

Use protocols for: complex features, major refactorings, cross-cutting changes, multi-session work needing progress tracking. For simple tasks, use [`/develop`][develop] directly.

## Pipeline Overview

```
/create-prd ──> /create-spec (optional) ──> /create-protocol ──> /process-protocol ──> /merge-protocol
                                                                        │                     │
                                                                   /defer (backlog)    /update-memory-bank <protocol>
```

Each stage has a **skill** (thin entry point) and a **workflow** (engine-driven definition in [`.workflows/`][workflows]).

## Stage 1: Planning

### `/create-prd "feature description"` (optional formal step)

Creates a Product Requirements Document — **what** to build and **why**, not how.

The workflow creates a protocol directory (`.protocols/NNNN-feature-name/`), asks clarifying questions, then generates a PRD with mandatory sections: Introduction, Goals, User Stories, Functional Requirements, Non-Goals, Design Considerations, Technical Considerations, Success Metrics, Open Questions.

Output: `.protocols/NNNN-feature-name/prd.md`

This step is optional — [`/create-protocol`][create-protocol] can create the PRD itself from a free-form discussion. Use [`/create-prd`][create-prd] when you want a more structured requirements gathering process.

### `/create-spec NNNN` (optional)

Creates a Technical Specification from an existing PRD — **how** to build it. Locates the protocol directory by number, reads `prd.md`, analyzes the codebase, asks technical questions, generates a spec with architecture, data model, API design, code snippets.

Output: `.protocols/NNNN-feature-name/spec.md`

## Stage 2: Protocol Creation

### `/create-protocol NNNN` or `/create-protocol "feature description"`

If given a protocol number, finds the existing directory with `prd.md` (created by [`/create-prd`][create-prd]). If given a feature description, creates a new protocol directory and generates `prd.md` from the discussion.

Then generates the implementation plan: ADR, step files, and context.

**What gets created:**

```
.protocols/NNNN-feature-name/
├── prd.md                    # Frozen requirements snapshot
├── plan.md                   # ADR + progress tracking (single source of truth)
├── 01-setup.md               # Step file (root-level)
├── 02-infrastructure/        # Group folder (scopes context)
│   ├── _context/             # Shared context for this group only
│   │   └── research.md
│   ├── 01-database.md        # Step file (grouped)
│   └── 02-cache.md
├── 03-api.md
└── _context/                 # Shared context for entire protocol
    └── architecture-notes.md
```

**Key concepts:**

-   **plan.md** is the single source of truth — contains an ADR (Context, Decision, Rationale, Consequences) plus progress checkboxes
-   **Step files** are focused work units with: Objective, Tasks (checkboxes), Implementation Notes, Verification (bash commands), Context, Findings, Memory Bank Impact
-   **Groups** are organizational folders that scope `_context/` loading but don't affect execution order — all steps run sequentially
-   **`_context/`** directories hold shared research: protocol-wide at root, group-scoped inside group folders

The command does NOT start execution — the user reviews the plan and runs [`/process-protocol`][process-protocol] when ready.

## Stage 3: Execution

### `/process-protocol NNNN`

The core execution engine. Runs steps sequentially in an isolated git worktree.

**Rule: protocol = 1 branch = 1 worktree.** All implementation happens in `.worktrees/protocol-NNNN`, not in the main checkout.

**Setup:**

1. Read `plan.md`, find next incomplete step
2. Create worktree: `git worktree add .worktrees/protocol-NNNN -b protocol-NNNN develop`
3. All subsequent work happens inside the worktree

**Per step (repeated):**

1. **Load step** — read ONLY the current step file (not others)
2. **Load context** — [`/load-context`][load-context] loads `_context/` files (group-scoped first, then protocol-wide)
3. **Execute** — delegates to [`/develop`][develop] in Protocol mode (explore → plan → implement)
4. **Record findings** — discoveries go into the step's `## Findings` section with tags:
    - `[DECISION]` — architectural choice made during implementation
    - `[GOTCHA]` — unexpected issue or non-obvious behavior
    - `[REUSE]` — pattern worth documenting for other features
    - `[DEFER]` — out-of-scope item → sent to backlog via [`/defer`][defer]
5. **Validate** — all subtasks `[x]`, tests pass
6. **Code review** — [`/code-review`][code-review] with triage (FIX / DEFER / ACCEPT)
7. **Commit** — [`/commit`][commit] (mandatory, each step = one commit)
8. **Mark complete** — update `plan.md` with `[x]`

**Progress markers** in `plan.md`:

-   `[ ]` not started
-   `[~]` in progress
-   `[x]` complete (committed + reviewed)
-   `[-]` blocked

Execution can be paused and resumed across sessions — `plan.md` tracks state.

## Stage 4: Merge

### `/merge-protocol .protocols/NNNN-feature/`

Merges the protocol's worktree branch into `develop` after final verification.

1. Verify all steps are `[x]` in `plan.md`
2. Run tests in the worktree
3. Run [`/code-review`][code-review] on all cumulative changes (`git diff develop`)
4. Fix issues, re-review until clean
5. User confirms merge
6. Rebase onto develop, merge with `--no-ff`
7. Run tests on develop
8. Clean up worktree and branch
9. Mark protocol status `Complete`

## Stage 5: Knowledge Capture

### `/update-memory-bank .protocols/NNNN-feature/`

Transforms protocol findings into permanent Memory Bank knowledge.

1. **Collect** — gather `## Findings` and `## Memory Bank Impact` from all step files, plus `_context/findings.md`
2. **Triage** — keep only what affects future decisions, is not obvious from code, or is a repeatable pattern. Discard task-specific details.
3. **Transform** — rewrite findings as knowledge, not history. Example: "Tried redis for sessions → switched to postgres (deployment complexity)" becomes "Sessions use postgres; redis rejected for deployment complexity."
4. **Apply** — update Memory Bank files using the standard update process
5. **Mark** — check off impact items in step files

## Backlog System ([`/defer`][defer])

The defer skill manages out-of-scope discoveries during protocol execution and code review.

### When it's used

-   During [`/process-protocol`][process-protocol] — finding tagged `[DEFER]` in a step
-   During [`/code-review`][code-review] — issue triaged as DEFER
-   Standalone — any time you want to record a task for later

### What it creates

```
.backlog/
└── items/
    ├── fix-n-plus-one-query-in-tasks-api.md
    ├── add-rate-limiting-to-public-endpoints.md
    └── investigate-flaky-test-in-auth-module.md
```

Each item has frontmatter: `type` (bug/debt/idea/risk), `priority` (p0-p3), `status` (open/closed), and optional `area`, `effort`, `origin`.

### Commands

```
/defer "title" --type debt --priority p2 --area api    # Create item
/defer list --type bug --status open                   # Filter items
/defer view --group-by priority                        # Dashboard
/defer close <slug>                                    # Archive resolved item
```

When deferred from a protocol step, a `[DEFER]` link is automatically inserted into the step's Findings section.

## Quick Reference

| Skill | Who calls | Input | Output |
|-------|-----------|-------|--------|
| [`/create-prd`][create-prd] | User | Feature description | `.protocols/NNNN/prd.md` (creates protocol dir) |
| [`/create-spec`][create-spec] | User | Protocol number | `.protocols/NNNN/spec.md` (optional) |
| [`/create-protocol`][create-protocol] | User | Protocol number or feature description | `plan.md` + step files (creates prd.md if needed) |
| [`/process-protocol`][process-protocol] | User | Protocol number | Executed steps in worktree |
| [`/merge-protocol`][merge-protocol] | User (after all steps complete) | Protocol number | Merged to develop, worktree cleaned |
| [`/update-memory-bank`][update-memory-bank] | User (after merge) | Protocol path | Findings → Memory Bank knowledge |
| [`/defer`][defer] | Claude (during execution/review) | Title + metadata | Backlog item |
| [`/load-context`][load-context] | Claude (per step) | Protocol dir + step path | Loaded `_context/` files |

<!-- Skill folders -->
[create-prd]: ../static/skills/create-prd/
[create-spec]: ../static/skills/create-spec/
[create-protocol]: ../static/skills/create-protocol/
[process-protocol]: ../static/skills/process-protocol/
[merge-protocol]: ../static/skills/merge-protocol/
[update-memory-bank]: ../static/skills/update-memory-bank/
[develop]: ../static/skills/develop/
[code-review]: ../static/skills/code-review/
[commit]: ../static/skills/commit/
[defer]: ../static/skills/defer/
[load-context]: ../static/skills/load-context/

<!-- Workflow folders -->
[workflows]: ../static/workflows/
