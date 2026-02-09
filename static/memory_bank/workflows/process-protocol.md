# Process Protocol Workflow

## Goal

Execute protocol steps systematically in isolated git worktrees with quality checks and progress tracking.

## When to Use

-   After creating a protocol with `/create-protocol`
-   To implement complex features step by step
-   To resume work on a multi-session feature

## Step 1: Load Protocol

```bash
/prime
# Read protocol plan.md
```

From plan.md extract:

-   Protocol status (must be Draft or In Progress)
-   **Branching strategy** (`Branching` field, default: `per-protocol`)
-   Next step: first `[ ]` or `[~]` in Progress section
-   Group membership (if `per-group`)

Update protocol status to `In Progress` if currently `Draft`.

**Do not read step files yet.** Just identify the next step from plan.md.

## Step 2: Load Current Step

Read ONLY the current step file. Follow the link from plan.md Progress:

```
Flat:    .protocols/0001-feature/03-step-name.md
Folders: .protocols/0001-feature/01-group/01-step.md
```

From the step file, extract:

-   Current subtask (first `[ ]` or `[~]` in Tasks)
-   Implementation Notes
-   Context section (brief summary already in step file)

List available context files (**don't read, just note paths**):

-   `_context/` alongside step file (group-level for folders)
-   Protocol root `_context/`
-   Files matching `_context/step-NN-*` for current step number

These paths will be passed to sub-agents in Step 4. They read them if needed.

**Do not read other step files or `_context/` contents.** Sub-agents will access reference materials directly.

## Step 3: Setup Worktree

Isolate work in a dedicated git worktree before executing subtasks.

### Ensure develop branch exists

Check if `develop` branch exists:

```bash
git branch --list develop
```

If it doesn't exist, ask the user:

```
develop branch not found
───────────────────────────
Current branch: feature-auth
Default branch: main

Which branch should develop be based on?
1. main
2. feature-auth (current branch)
3. Other — specify branch name
```

Then create:

```bash
git branch develop <chosen-branch>
```

This is a one-time setup. Once `develop` exists, all protocols use it as the integration branch.

### Determine branch names

```
PROJECT_ROOT = main checkout directory (where .protocols/ lives)
PROTOCOL_NUM = from protocol directory name (e.g., 0001)
STEP_NUM = from step file name (e.g., 03)
STRATEGY = plan.md Branching field, default "per-protocol"

STEP_BRANCH = "protocol-${PROTOCOL_NUM}-step-${STEP_NUM}"

if STRATEGY == "per-protocol":
    PARENT_BRANCH = "protocol-${PROTOCOL_NUM}"
elif STRATEGY == "per-group":
    PARENT_BRANCH = "protocol-${PROTOCOL_NUM}-group-${GROUP_NUM}"
elif STRATEGY == "per-step":
    PARENT_BRANCH = "develop"
```

### Create worktree

For `per-protocol` / `per-group` — create parent branch first (if it doesn't exist yet):

```bash
mkdir -p .worktrees
git worktree add ".worktrees/${PARENT_BRANCH}" -b "${PARENT_BRANCH}" develop
```

Then create step worktree:

```bash
git worktree add ".worktrees/${STEP_BRANCH}" -b "${STEP_BRANCH}" "${PARENT_BRANCH}"
```

For `per-step` — create step worktree directly from develop:

```bash
mkdir -p .worktrees
git worktree add ".worktrees/${STEP_BRANCH}" -b "${STEP_BRANCH}" develop
```

### Copy environment files

If the project uses `.env` files, copy them into the worktree (they are gitignored):

```bash
for f in .env .env.local .env.test; do
  [ -f "$f" ] && cp "$f" ".worktrees/${STEP_BRANCH}/$f"
done
```

### If worktree already exists

| Step status in plan.md    | Action                                |
| ------------------------- | ------------------------------------- |
| `[~]` In Progress         | Resume in existing worktree           |
| `[x]` Complete            | Resume for review or changes          |
| `[✓]` Approved (per-step) | Ready for merge, or make more changes |
| Unknown                   | Ask user: resume or recreate          |

### Report

```
Worktree Ready
─────────────────────────
Strategy: per-protocol
Branch: protocol-0001-step-03
Parent: protocol-0001
Location: .worktrees/protocol-0001-step-03
```

**All subsequent work happens in the worktree directory** — both code changes and protocol file edits (step file, `_context/`, plan.md). Do not edit `.protocols/` in the main checkout.

## Step 4: Execute Subtasks

For each subtask in the step file's Tasks section:

1. Mark subtask `[~]` in step file (in worktree)
2. Follow [Development Workflow](./development-workflow.md) in **protocol mode**. Pass context:
    - **Task** (text): subtask description
    - **Key context** (text): relevant facts from step file's Implementation Notes, Context, and Findings
    - **Reference files** (paths): `_context/` files noted in Step 2 — sub-agents read them if needed
    - Include only what affects the current subtask.
3. When development workflow completes, collect its output (modified files + discoveries)
4. Record discoveries — see [Record findings](#record-findings) below
5. Mark subtask `[x]`
6. Proceed to next subtask

Repeat until all subtasks complete.

### Record findings

After each subtask, take discoveries returned by the development workflow and append them to the step file's `## Findings` section. Tag where appropriate:

-   `[DECISION]` — decisions made during implementation
-   `[GOTCHA]` — pitfalls, unexpected behavior
-   `[REUSE]` — reusable patterns or utilities found

**Promotion rule:** if a finding is about the **system** (not just about the current task), also append it to `_context/findings.md` grouped by step:

```markdown
# Findings

## From Step 01: Schema Definition

-   [DECISION] Postgres for sessions instead of redis (simpler deployment)

## From Step 03: API Endpoints

-   Rate limiting already exists in middleware, no need for per-endpoint
```

Create `_context/findings.md` on first promotion. Don't create it if all findings are task-local.

### Subtask markers

| Marker | Meaning     |
| ------ | ----------- |
| `[ ]`  | Pending     |
| `[~]`  | In progress |
| `[x]`  | Complete    |
| `[-]`  | Blocked     |

## Step 5: Validate Step Completion

Before marking step complete, verify:

| Check              | Method               | If failed            |
| ------------------ | -------------------- | -------------------- |
| All subtasks `[x]` | Parse step file      | Do not mark complete |
| Tests pass         | Run test suite       | Mark `[-]` blocked   |
| No blockers        | Check review results | Mark `[-]` blocked   |

If validation fails, surface the issue to the user and do not proceed.

## Step 6: Mark Step Complete

Update **only plan.md** (step files don't track status):

```markdown
-   [x] [Step Name](./03-step-name.md) — 6h est / 5h actual
```

Commit all changes in worktree using `/commit`. If `/commit` is unavailable, follow [Commit Message Rules](./commit-message-rules.md) manually.

## Step 7: Merge Step

Behavior depends on branching strategy.

---

### per-protocol / per-group — Fast Merge

Step merges into parent branch **without code review or user confirmation**. Code review happens later at protocol/group level via `/merge-protocol`.

**Merge:**

```bash
cd ".worktrees/${STEP_BRANCH}"
git status   # must be clean
git rebase "${PARENT_BRANCH}"

cd ".worktrees/${PARENT_BRANCH}"
git merge --no-ff "${STEP_BRANCH}" -m "feat: step ${STEP_NUM} — ${STEP_NAME}"
```

**Cleanup:**

```bash
cd "${PROJECT_ROOT}"
git worktree remove ".worktrees/${STEP_BRANCH}"
git branch -d "${STEP_BRANCH}"
```

**Update plan.md:** `- [M] [Step Name](./03-step-name.md) — 6h est / 5h actual`

```
Step Merged (fast)
─────────────────────────
Step: protocol-0001-step-03 → protocol-0001
Protocol worktree remains: .worktrees/protocol-0001
```

→ Proceed to Step 8.

---

### per-step — Review + Approval + User Confirmation

Step merges into develop **with code review and explicit user approval**.

**7a. Code Review**

Invoke @code-reviewer on all modified files in worktree.

| Review result        | Action                             |
| -------------------- | ---------------------------------- |
| No BLOCKER/REQUIRED  | Proceed to 7b                      |
| Has BLOCKER/REQUIRED | Fix in worktree, commit, re-review |
| Has SUGGESTION       | Apply or document reason to skip   |

Review iteration loop: `Review → Fix → Commit → Re-review → ... → Clean`

**7b. Mark Approved**

After clean review, update plan.md:

```markdown
-   [✓] [Step Name](./03-step-name.md) — 6h est / 5h actual
```

Worktree is preserved. User can still request more review iterations.

**7c. Ask User**

```
Step Complete and Approved
─────────────────────────────
Branch: protocol-0001-step-03
Code review: PASSED
Tests: PASSED

Options:
1. [merge]  - Merge to develop and cleanup worktree
2. [wait]   - Keep worktree, merge later with /merge-step
3. [review] - Run another code review cycle
```

| Response | Action                           |
| -------- | -------------------------------- |
| merge    | Proceed to 7d                    |
| wait     | Keep worktree, proceed to Step 8 |
| review   | Return to 7a                     |

Default: **wait** (preserve worktree).

**7d. Merge to Develop**

```bash
cd ".worktrees/${STEP_BRANCH}"
git rebase develop

cd "${PROJECT_ROOT}"
git checkout develop
git merge --no-ff "${STEP_BRANCH}" -m "feat: protocol-${PROTOCOL_NUM} step ${STEP_NUM} — ${STEP_NAME}"
```

Run tests on develop. If tests fail: `git reset --hard HEAD~1`, fix in worktree, retry.

**Cleanup:**

```bash
git worktree remove ".worktrees/${STEP_BRANCH}"
git branch -d "${STEP_BRANCH}"
```

Update plan.md: `- [M] [Step Name](./03-step-name.md) — 6h est / 5h actual`

---

## Step 8: Next Step or Pause

**If continuing:** return to Step 1 (next `[ ]` step in plan.md).

**If pausing:**

-   Ensure plan.md Progress reflects current status
-   Note in step file which subtask you stopped at (if mid-step)
-   Commit worktree state

**If all steps complete:** proceed to Protocol Completion below.

## Protocol Completion

When all steps in plan.md are marked `[M]`:

### 1. Merge to Develop (per-protocol / per-group only)

The protocol/group branch must still be merged into develop:

```bash
/merge-protocol .protocols/0001-feature/
```

This runs code review on all cumulative changes, then merges with user confirmation. See `/merge-protocol` command for details.

For `per-step` — steps are already merged, skip this.

### 2. Update Memory Bank

```bash
/update-memory-bank-protocol .protocols/NNNN-feature/
```

This runs in an isolated context: collects findings from all step files, triages, transforms, and applies to Memory Bank.

### 3. Mark Protocol Complete

```markdown
**Status**: Complete
```

## Handling Issues

**Blocker in current step:**

1. Document the blocker in step file
2. Mark step `[-]` in plan.md
3. Skip to next unblocked step (if independent)
4. Return when resolved

**Task failure:**

1. Document failure and error
2. Attempt fix
3. If not fixable, surface to user
4. Don't proceed until resolved

**Scope change:**

1. Update ADR in plan.md with new context
2. Add/modify steps as needed
3. Update estimates
4. Continue execution

## Step Status Reference

Step status in plan.md:

```
per-protocol / per-group:  [ ] → [~] → [x] → [M]
per-step:                  [ ] → [~] → [x] → [✓] → [M]
                                         ↓
                                        [-] (blocked)
```

`[✓]` (Approved) is only used with `per-step`. With `per-protocol`/`per-group`, steps go directly `[x]` → `[M]` via fast merge.

## Related Documentation

-   [Git Worktree Workflow](./git-worktree-workflow.md) - Worktree setup, merge, cleanup details
-   [Create Protocol](./create-protocol.md) - Create new protocols
-   [Development Workflow](./development-workflow.md) - Mandatory for all subtasks
-   [Update Memory Bank](./update-memory-bank.md) - Documentation update process
