# Git Worktree Workflow

## Goal

Isolate protocol step execution in separate git worktrees with configurable branching strategies for safe, reversible changes and clean merge history.

## When to Use

-   Processing protocol steps (called from process-protocol.md)
-   Any multi-step feature requiring isolation
-   Parallel development of independent tasks

## Benefits

| Benefit        | Description                                    |
| -------------- | ---------------------------------------------- |
| Isolation      | Step failures don't affect main checkout       |
| Clean history  | Each step = one merge commit                   |
| Easy rollback  | Just delete worktree, no cleanup needed        |
| Parallel work  | Multiple steps can run simultaneously (future) |
| Deferred merge | Review iterations without losing work          |

---

## Branching Strategies

Read `branching` from protocol `plan.md` metadata. Default: `per-protocol`.

```
branching = protocol.metadata.branching ?? "per-protocol"
```

### per-protocol (default)

One protocol branch, step branches merge into it. Protocol branch merges into develop with full review.

```
develop
  └── protocol-0001                          ← protocol branch (worktree)
        ├── protocol-0001-step-01            ← step branch → protocol (fast)
        ├── protocol-0001-step-02            ← step branch → protocol (fast)
        └── protocol-0001-step-03            ← step branch → protocol (fast)
                    │
                    ▼
        protocol-0001 → develop              ← review + approval
```

**Use when:** Steps are parts of one feature, merging individual steps is not useful.

### per-step

Step branches merge directly into develop with review. No protocol branch.

```
develop
  ├── protocol-0002-step-01 → develop       ← review + approval
  ├── protocol-0002-step-02 → develop       ← review + approval
  └── protocol-0002-step-03 → develop       ← review + approval
```

**Use when:** Steps are independent and self-contained. Each step is valuable on its own.

### per-group

Group branches collect related steps. Each group merges into develop with review.

```
develop
  ├── protocol-0003-group-01                 ← group branch (worktree)
  │     ├── protocol-0003-step-01            ← step → group (fast)
  │     └── protocol-0003-step-02            ← step → group (fast)
  │               │
  │               ▼
  │     group-01 → develop                   ← review + approval
  │
  └── protocol-0003-group-02                 ← group branch (worktree)
        ├── protocol-0003-step-03            ← step → group (fast)
        └── protocol-0003-step-04            ← step → group (fast)
                    │
                    ▼
        group-02 → develop                   ← review + approval
```

**Use when:** Protocol has clusters of related steps, but clusters are independent of each other.

### Merge behavior summary

| Strategy     | Step merges into | Review on step merge | Final merge to develop | Review on final |
| ------------ | ---------------- | -------------------- | ---------------------- | --------------- |
| per-protocol | protocol branch  | No (fast)            | /merge-protocol        | Yes + approval  |
| per-step     | develop          | Yes + approval       | N/A                    | N/A             |
| per-group    | group branch     | No (fast)            | /merge-protocol        | Yes + approval  |

**Fast merge** = tests pass → merge immediately, no user confirmation needed.
**Review + approval** = code review + user confirmation before merge.

---

## Step Status and Worktree Lifecycle

Worktrees follow the step status lifecycle:

```
Step Status          Worktree State
───────────────────────────────────────────
[ ] Not Started      No worktree
[~] In Progress      Worktree active, work ongoing
[x] Complete         Worktree active, tests pass
[✓] Approved         Worktree active, review passed (per-step only)
[M] Merged           Worktree removed
[-] Blocked          Worktree active, awaiting fix
```

**per-protocol/per-group:** Steps go `[x]` → `[M]` (fast merge into protocol/group branch, no approval needed).
**per-step:** Steps go `[x]` → `[✓]` → `[M]` (with review + approval before merge into develop).

### Protocol/Group Branch Status

| Status   | Meaning                               |
| -------- | ------------------------------------- |
| Active   | Steps being developed                 |
| Ready    | All steps merged, ready for review    |
| Approved | Review passed, ready to merge         |
| Merged   | Merged into develop, worktree removed |

## Prerequisites

Before starting:

-   [ ] Git repository initialized
-   [ ] `develop` branch exists and is clean
-   [ ] No uncommitted changes in main checkout

## Directory Structure

```
project/
├── .worktrees/                              # Worktree directory (gitignored)
│   ├── protocol-0001/                       # Protocol branch worktree (per-protocol)
│   ├── protocol-0001-step-01/               # Step worktree
│   ├── protocol-0001-step-02/               # Step worktree
│   ├── protocol-0003-group-01/              # Group branch worktree (per-group)
│   └── ...
├── .protocols/
│   └── 0001-feature/
│       ├── plan.md
│       └── 01-step-name.md
└── (main checkout - develop)
```

**Add to .gitignore:**

```
.worktrees/
```

---

## Phase 1: Setup

Called after loading protocol step (process-protocol.md Step 2).

### Step 1.1: Determine Strategy and Branch Names

```
PROTOCOL_NUM="0001"
STEP_NUM="01"
STRATEGY = plan.md.branching ?? "per-protocol"

# Step branch name (always created)
STEP_BRANCH="protocol-${PROTOCOL_NUM}-step-${STEP_NUM}"

# Parent branch (what the step branches from)
if STRATEGY == "per-protocol":
    PARENT_BRANCH="protocol-${PROTOCOL_NUM}"
elif STRATEGY == "per-group":
    GROUP_NUM = group number for this step from plan.md
    PARENT_BRANCH="protocol-${PROTOCOL_NUM}-group-${GROUP_NUM}"
elif STRATEGY == "per-step":
    PARENT_BRANCH="develop"
```

### Step 1.2: Create Parent Branch (per-protocol / per-group only)

Skip this step for `per-step` strategy.

```bash
PARENT_BRANCH="protocol-${PROTOCOL_NUM}"  # or group branch

# Check if parent branch worktree exists
git worktree list | grep "${PARENT_BRANCH}"

# If not, create it
mkdir -p .worktrees
git worktree add ".worktrees/${PARENT_BRANCH}" -b "${PARENT_BRANCH}" develop
```

The parent branch worktree persists across all steps in the protocol/group.

### Step 1.3: Check Existing Step Worktree

```bash
git worktree list | grep "${STEP_BRANCH}"
```

**If exists:**

| Step Status       | Worktree State   | Action                                  |
| ----------------- | ---------------- | --------------------------------------- |
| `[~]` In Progress | Active           | Resume work in existing worktree        |
| `[x]` Complete    | Active           | Resume for review or additional changes |
| `[✓]` Approved    | Active           | Ready for merge, or make more changes   |
| `[M]` Merged      | Should not exist | Run cleanup if stale                    |
| Unknown           | Active           | Ask user: resume or recreate            |

### Step 1.4: Create Step Worktree

```bash
mkdir -p .worktrees
git worktree add ".worktrees/${STEP_BRANCH}" -b "${STEP_BRANCH}" "${PARENT_BRANCH}"
```

Note: step branch is created from `PARENT_BRANCH` (protocol/group branch or develop).

**On error:**

| Error                    | Cause                   | Solution                                  |
| ------------------------ | ----------------------- | ----------------------------------------- |
| `branch already exists`  | Previous incomplete run | `git branch -D ${STEP_BRANCH}` then retry |
| `not a valid reference`  | Parent doesn't exist    | Create parent branch first (Step 1.2)     |
| `is already checked out` | Branch in use elsewhere | Find and remove stale worktree            |

### Step 1.5: Copy Environment Files

Worktrees don't include gitignored files. Copy `.env*` files from the main checkout:

```bash
for f in .env .env.local .env.test .env.development .env.production; do
  [ -f "$f" ] && cp "$f" ".worktrees/${STEP_BRANCH}/$f"
done
```

Skip this step if the project has no `.env` files.

### Step 1.6: Verify Setup

```bash
ls -la ".worktrees/${STEP_BRANCH}"
git -C ".worktrees/${STEP_BRANCH}" branch --show-current
```

### Step 1.7: Report Context Switch

```
Worktree Setup Complete
─────────────────────────
Strategy: per-protocol
Branch: protocol-0001-step-01
Parent: protocol-0001
Location: .worktrees/protocol-0001-step-01

All subsequent changes will be made in this worktree.
```

---

## Phase 2: Working in Worktree

All development-workflow.md execution happens in the worktree.

### Important Paths

When executing in worktree, paths are relative to worktree root:

| Resource       | Path in Worktree                    |
| -------------- | ----------------------------------- |
| Source code    | `.worktrees/{branch}/src/`          |
| Tests          | `.worktrees/{branch}/tests/`        |
| Memory Bank    | `.worktrees/{branch}/.memory_bank/` |
| Protocol files | `.worktrees/{branch}/.protocols/`   |

### Committing Changes

Commit frequently within the worktree. Use `/commit` skill or follow its [Commit Message Rules](commit-message-rules.md).

```bash
cd ".worktrees/${STEP_BRANCH}"
git add <specific-files>
git commit -m "feat: description of change"
```

### Running Tests

All tests run in worktree context:

```bash
cd ".worktrees/${STEP_BRANCH}"

# Run tests (project-specific command)
npm test        # Node.js
pytest          # Python
go test ./...   # Go
```

---

## Phase 2.5: Step Completion

After step completion (`[x]`), behavior depends on branching strategy.

### per-protocol / per-group: Fast Merge

Step merges into parent branch (protocol/group) **without review or user confirmation**.

Requirements:

-   All subtasks complete
-   Tests pass in worktree
-   No uncommitted changes

```bash
cd ".worktrees/${STEP_BRANCH}"

# Verify clean state
git status  # Must be clean

# Run tests
npm test

# Rebase onto parent
git rebase "${PARENT_BRANCH}"

# Merge into parent (in parent worktree)
cd ".worktrees/${PARENT_BRANCH}"
git merge --no-ff "${STEP_BRANCH}" -m "feat: step ${STEP_NUM} — ${STEP_NAME}"

# Cleanup step worktree
cd /path/to/project
git worktree remove ".worktrees/${STEP_BRANCH}"
git branch -d "${STEP_BRANCH}"
```

Update plan.md: `- [M] Step N: Title`

**No user confirmation needed.** Protocol/group branch is the isolation boundary.

Report:

```
Step Merged (fast)
─────────────────────────
Step: protocol-0001-step-01 → protocol-0001
Tests: PASS

Step worktree removed.
Protocol branch worktree remains: .worktrees/protocol-0001

Ready for next step.
```

### per-step: Review + Approval

Step merges into develop **with review and user confirmation**.

Follow the full approval flow:

1. **Code Review** — invoke @code-reviewer
2. **Fix/Re-review loop** — until no BLOCKER/REQUIRED
3. **Mark Approved** — `[✓]`
4. **User Confirmation** — ask merge/wait/review
5. **Merge** — only on explicit approval (Phase 3)

See [process-protocol.md](./process-protocol.md) Steps 5.5 and 5.6 for details.

---

## Phase 3: Merge to Develop

### For per-step: Merge Step Branch

**Called only after explicit merge approval** (process-protocol.md Step 5.6).

#### 3.1: Final Verification

```bash
cd ".worktrees/${STEP_BRANCH}"

git status        # Must be clean
npm test          # Tests must pass
npm run lint      # Lint must pass
```

**DO NOT proceed if any check fails.**

#### 3.2: Rebase onto Develop

```bash
cd ".worktrees/${STEP_BRANCH}"
git fetch origin develop
git rebase develop
```

**On conflict:** Resolve, `git add .`, `git rebase --continue`, re-run tests.

#### 3.3: Merge

```bash
cd /path/to/project
git checkout develop
git merge --no-ff "${STEP_BRANCH}" -m "feat: protocol-${PROTOCOL_NUM} step ${STEP_NUM} — ${STEP_NAME}"
npm test  # Verify on develop
```

**If tests fail:** `git reset --hard HEAD~1`, fix in worktree, retry.

#### 3.4: Cleanup

```bash
git worktree remove ".worktrees/${STEP_BRANCH}"
git branch -d "${STEP_BRANCH}"
```

Update plan.md: `- [M] Step N: Title`

### For per-protocol / per-group: Merge Parent Branch

**Called via `/merge-protocol` command after all steps in protocol/group are merged into parent branch.**

#### 3.1: Final Verification

```bash
cd ".worktrees/${PARENT_BRANCH}"

git status        # Must be clean
npm test          # Full test suite
npm run lint      # Lint must pass
```

#### 3.2: Code Review

Run @code-reviewer on all changes vs develop:

```bash
cd ".worktrees/${PARENT_BRANCH}"
git diff develop --stat  # Show all changes
```

Review iteration loop: Review → Fix → Commit → Re-review → ... → Clean

#### 3.3: User Confirmation

```
Protocol Ready for Merge
─────────────────────────────
Branch: protocol-0001
Steps merged: 3/3
Changes vs develop: 15 files, +450/-120

Code review: PASSED
Tests: PASSED

Ready to merge to develop?

Options:
1. [merge]  - Merge now
2. [wait]   - Keep branch, merge later
3. [review] - Run another code review
```

#### 3.4: Rebase and Merge

```bash
cd ".worktrees/${PARENT_BRANCH}"
git rebase develop

cd /path/to/project
git checkout develop
git merge --no-ff "${PARENT_BRANCH}" -m "feat: protocol-${PROTOCOL_NUM} — ${PROTOCOL_NAME}"
npm test  # Verify on develop
```

**If tests fail:** `git reset --hard HEAD~1`, fix in parent worktree, retry.

#### 3.5: Cleanup

```bash
git worktree remove ".worktrees/${PARENT_BRANCH}"
git branch -d "${PARENT_BRANCH}"
```

Update plan.md status: `Complete`

---

## Conflict Resolution

### During Rebase

```bash
git status
git add <resolved-file>
git rebase --continue
```

### Complex Conflicts

1. **Document the conflict:**

    ```
    Conflict in: src/api/users.ts
    Our change: Added validation
    Their change: Refactored to async
    ```

2. **Analyze both changes:**

    - Read the full diff for both sides
    - Understand intent of each change

3. **Resolve preserving both intents**

4. **Test thoroughly after resolution**

### When to Escalate

Escalate to user when:

-   Conflict involves architectural decisions
-   Multiple valid resolution approaches exist
-   Changes contradict each other semantically
-   Unsure about business logic

---

## Rollback Procedures

### Rollback Uncommitted Changes

```bash
cd ".worktrees/${BRANCH_NAME}"
git checkout -- .
git clean -fd
```

### Rollback Entire Step (Before Merge)

```bash
git worktree remove --force ".worktrees/${STEP_BRANCH}"
git branch -D "${STEP_BRANCH}"
```

### Rollback After Step Merge to Parent

```bash
# In parent branch worktree
cd ".worktrees/${PARENT_BRANCH}"
git revert -m 1 <merge-commit-hash>
```

### Rollback After Merge to Develop

```bash
git checkout develop
git revert -m 1 <merge-commit-hash>
```

---

## Error Recovery

### Stale Worktree

```bash
git worktree prune
```

### Worktree on Wrong Branch

```bash
cd ".worktrees/${BRANCH_NAME}"
git checkout "${BRANCH_NAME}"
```

### Detached HEAD in Worktree

```bash
cd ".worktrees/${BRANCH_NAME}"
git checkout -B "${BRANCH_NAME}"
```

### Corrupted Worktree

```bash
git worktree remove --force ".worktrees/${BRANCH_NAME}"
git worktree add ".worktrees/${BRANCH_NAME}" -b "${BRANCH_NAME}" "${PARENT_BRANCH}"
```

---

## Best Practices

### DO

-   Commit frequently in worktree
-   Run tests before merge
-   Follow [Commit Message Rules](commit-message-rules.md)
-   Keep steps small and focused
-   Clean up step worktrees after merge
-   Use `per-protocol` as default strategy

### DON'T

-   Work directly on develop
-   Leave worktrees after merge
-   Skip rebase before merge
-   Ignore test failures
-   Force push to shared branches
-   Change branching strategy mid-protocol

---

## Quick Reference

### per-protocol

```bash
# Setup protocol branch (once)
git worktree add ".worktrees/protocol-0001" -b "protocol-0001" develop

# Setup step worktree
git worktree add ".worktrees/protocol-0001-step-01" -b "protocol-0001-step-01" "protocol-0001"

# Work in step
cd ".worktrees/protocol-0001-step-01"
git add <files> && git commit -m "feat: description"

# Fast merge step → protocol
cd ".worktrees/protocol-0001"
git merge --no-ff "protocol-0001-step-01" -m "feat: step 01 — title"
git worktree remove ".worktrees/protocol-0001-step-01"
git branch -d "protocol-0001-step-01"

# Final merge protocol → develop (after all steps)
cd /project && git checkout develop
git merge --no-ff "protocol-0001" -m "feat: protocol-0001 — name"
git worktree remove ".worktrees/protocol-0001"
git branch -d "protocol-0001"
```

### per-step

```bash
# Setup step worktree
git worktree add ".worktrees/protocol-0002-step-01" -b "protocol-0002-step-01" develop

# Work in step
cd ".worktrees/protocol-0002-step-01"
git add <files> && git commit -m "feat: description"

# Merge step → develop (after review)
cd /project && git checkout develop
git merge --no-ff "protocol-0002-step-01" -m "feat: protocol-0002 step 01 — title"
git worktree remove ".worktrees/protocol-0002-step-01"
git branch -d "protocol-0002-step-01"
```

---

## Related Documentation

-   [Process Protocol](./process-protocol.md) - Protocol execution workflow
-   [Development Workflow](./development-workflow.md) - Task implementation workflow
-   [Testing Workflow](./testing-workflow.md) - Quality verification
