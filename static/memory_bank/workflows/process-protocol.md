# Process Protocol Workflow

## Goal

Execute protocol steps sequentially in an isolated git worktree with mandatory quality checks after each step.

## When to Use

-   After creating a protocol with `/create-protocol`
-   To implement complex features step by step
-   To resume work on a multi-session feature

## Core Rule

**Protocol = 1 branch = 1 worktree.** Steps are commits within that worktree. No exceptions.

## Flow Overview

```
Setup:
  Step 1: Load protocol
  Step 2: Load current step
  Step 3: Commit protocol files (if uncommitted)
  Step 4: Setup worktree

Per step (repeat):
  Step 5: Execute subtasks
  Step 6: Validate step
  Step 7: /code-review                             ← MANDATORY
  Step 8: /commit                                  ← MANDATORY
  Step 9: Mark [x], next step or finish

Finish:
  Step 10: /merge-protocol                         ← code review + merge to develop
```

---

## Step 1: Load Protocol

```
/prime
```

Read protocol plan.md. Extract:

-   Protocol status (must be Draft or In Progress)
-   Next step: first `[ ]` or `[~]` in Progress section (follow the markdown link — may be a root-level file like `./01-setup.md` or a grouped file like `./02-infrastructure/01-database.md`)

Update status to `In Progress` if currently `Draft`.

**Do not read step files yet.** Just identify the next step.

## Step 2: Load Current Step

Read ONLY the current step file (follow link from plan.md Progress).

Extract:

-   Current subtask (first `[ ]` or `[~]` in Tasks)
-   Implementation Notes
-   Context section

### Context

Per-step context is inline in the step file's `## Context` section.

Shared context (`_context/` files) will be loaded by the development workflow via `/load-context` in Step 5.

**Do not read other step files.**

## Step 3: Commit Protocol Files

Worktrees are created from `develop` — uncommitted files won't exist in them.

```bash
git status .protocols/${PROTOCOL_DIR}
```

If uncommitted protocol files exist:

```bash
git add .protocols/${PROTOCOL_DIR}
git commit -m "docs: create protocol ${PROTOCOL_NUM} — ${PROTOCOL_NAME}"
```

## Step 4: Setup Worktree

### Ensure develop branch exists

```bash
git branch --list develop
```

If missing, ask user which branch to base it on, then `git branch develop <chosen>`.

### Create worktree

```bash
BRANCH="protocol-${PROTOCOL_NUM}"

mkdir -p .worktrees
git worktree add ".worktrees/${BRANCH}" -b "${BRANCH}" develop
```

### Copy environment files

```bash
for f in .env .env.local .env.test .env.development .env.production; do
  [ -f "$f" ] && cp "$f" ".worktrees/${BRANCH}/$f"
done
```

### If worktree already exists

Protocol is being resumed. Work in the existing worktree. If state is unclear, ask user.

### Report

```
Worktree Ready
─────────────────────────
Branch: protocol-0001
Location: .worktrees/protocol-0001
```

**All subsequent work happens in the worktree directory.** Do not edit files in the main checkout.

---

## Step 5: Execute Subtasks

For each subtask in the step file:

1.  Mark subtask `[~]`
2.  Follow [Development Workflow](./development-workflow.md) in **Protocol mode**. Pass:
    -   **Task**: subtask description
    -   **Key context**: from Implementation Notes, Context, Findings
    -   **Protocol dir + step path**: for `/load-context`
3.  Collect output (modified files + discoveries)
4.  Record discoveries in step file `## Findings` section (see [below](#record-findings))
5.  Mark subtask `[x]`
6.  Proceed to next subtask

Repeat until all subtasks complete.

### Record findings

Append discoveries to step file's `## Findings`. Tag:

-   `[DECISION]` — decisions made during implementation
-   `[GOTCHA]` — pitfalls, unexpected behavior
-   `[REUSE]` — reusable patterns found

**Promotion:** if a finding is relevant beyond the current step, promote it:

-   **Group-scoped** (relevant to sibling steps) → `01-group/_context/findings.md`
-   **Protocol-scoped** (relevant to the whole protocol) → `_context/findings.md`

```markdown
# Findings

## From Step 03: API Endpoints

-   [GOTCHA] Rate limiting already in middleware, no per-endpoint needed
```

### Subtask markers

| Marker | Meaning     |
| ------ | ----------- |
| `[ ]`  | Pending     |
| `[~]`  | In progress |
| `[x]`  | Complete    |
| `[-]`  | Blocked     |

## Step 6: Validate Step Completion

| Check              | If failed            |
| ------------------ | -------------------- |
| All subtasks `[x]` | Do not mark complete |
| Tests pass         | Mark `[-]` blocked   |

If validation fails, surface the issue to the user and do not proceed.

## Step 7: Code Review (MANDATORY)

```
/code-review
```

Do not skip. Do not proceed without review.

| Review result        | Action                           |
| -------------------- | -------------------------------- |
| No BLOCKER/REQUIRED  | Proceed to commit                |
| Has BLOCKER/REQUIRED | Fix → re-review                  |
| Has SUGGESTION       | Apply or document reason to skip |

Loop until no BLOCKER/REQUIRED remains.

## Step 8: Commit (MANDATORY)

```
/commit
```

Do not skip. Do not proceed without committing.

The `/commit` skill reads the diff, composes a message following [Commit Message Rules](./commit-message-rules.md), and commits.

If `/commit` is unavailable, commit manually following the rules.

## Step 9: Mark Complete and Continue

Update plan.md:

```markdown
-   [x] [Step Name](./03-step-name.md) — 6h est / 5h actual
```

**If more steps remain:** return to Step 2.

**If pausing mid-protocol:**

-   Ensure plan.md reflects current status
-   `/commit` to save state

**If all steps are `[x]`:** proceed to Step 10.

---

## Step 10: Merge Protocol

```
/merge-protocol .protocols/NNNN-feature/
```

This command handles:

-   Final code review on all cumulative changes vs develop
-   Review iteration loop (fix → re-review → clean)
-   User confirmation before merge
-   Rebase + merge to develop
-   Worktree cleanup

After merge:

```
/update-memory-bank-protocol .protocols/NNNN-feature/
```

Update plan.md: `**Status**: Complete`

---

## Handling Issues

**Blocker in current step:**

1.  Document in step file
2.  Mark step `[-]` in plan.md
3.  Skip to next unblocked step if independent
4.  Return when resolved

**Task failure:**

1.  Document failure and error
2.  Attempt fix
3.  If not fixable, surface to user

**Scope change:**

1.  Update ADR in plan.md
2.  Add/modify steps
3.  Continue execution

## Step Status Reference

```
[ ] → [~] → [x]
```

| Marker | Meaning                         |
| ------ | ------------------------------- |
| `[ ]`  | Not started                     |
| `[~]`  | In progress                     |
| `[x]`  | Complete (committed + reviewed) |
| `[-]`  | Blocked                         |

Protocol status:

| Status      | Meaning                       |
| ----------- | ----------------------------- |
| Draft       | Created, not started          |
| In Progress | At least one step started     |
| Complete    | Merged to develop             |
| Blocked     | Step blocked, awaiting action |

## Related Documentation

-   [Create Protocol](./create-protocol.md) — Create new protocols
-   [Development Workflow](./development-workflow.md) — Mandatory for all subtasks
-   [Commit Message Rules](./commit-message-rules.md) — Commit conventions
-   [Git Worktree Workflow](./git-worktree-workflow.md) — Worktree management
-   [Update Memory Bank](./update-memory-bank.md) — Documentation updates
