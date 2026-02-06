# Git Worktree Workflow

## Goal

Isolate protocol step execution in separate git worktrees for safe, reversible changes with clean merge history.

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

## Step Status and Worktree Lifecycle

Worktrees follow the step status lifecycle:

```
Step Status          Worktree State
───────────────────────────────────────────
[ ] Not Started      No worktree
[~] In Progress      Worktree active, work ongoing
[x] Complete         Worktree active, tests pass
[✓] Approved         Worktree active, review passed
[M] Merged           Worktree removed
[-] Blocked          Worktree active, awaiting fix
```

**Key principle:** Worktree is preserved until explicit merge approval.

This allows:

-   Multiple code review iterations after step completion
-   Additional changes after approval
-   User-controlled merge timing

## Prerequisites

Before starting:

-   [ ] Git repository initialized
-   [ ] `develop` branch exists and is clean
-   [ ] No uncommitted changes in main checkout

## Directory Structure

```
project/
├── .worktrees/                    # Worktree directory (gitignored)
│   ├── protocol-0001-step-01/     # Worktree for step 1
│   ├── protocol-0001-step-02/     # Worktree for step 2
│   └── ...
├── .protocols/                    # Protocol definitions
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

## Phase 1: Setup Worktree

Called after loading protocol step (process-protocol.md Step 2).

### Step 1.1: Generate Branch Name

Format: `protocol-{NNNN}-step-{MM}`

Examples:

-   `protocol-0001-step-01`
-   `protocol-0023-step-03`

```bash
PROTOCOL_NUM="0001"
STEP_NUM="01"
BRANCH_NAME="protocol-${PROTOCOL_NUM}-step-${STEP_NUM}"
```

### Step 1.2: Check Existing Worktree

```bash
# Check if worktree already exists
git worktree list | grep "${BRANCH_NAME}"
```

**If exists:**

| Step Status       | Worktree State   | Action                                  |
| ----------------- | ---------------- | --------------------------------------- |
| `[~]` In Progress | Active           | Resume work in existing worktree        |
| `[x]` Complete    | Active           | Resume for review or additional changes |
| `[✓]` Approved    | Active           | Ready for merge, or make more changes   |
| `[M]` Merged      | Should not exist | Run cleanup if stale                    |
| Unknown           | Active           | Ask user: resume or recreate            |

### Step 1.3: Create Worktree

```bash
# Ensure .worktrees directory exists
mkdir -p .worktrees

# Create worktree with new branch from develop
git worktree add ".worktrees/${BRANCH_NAME}" -b "${BRANCH_NAME}" develop
```

**On error:**

| Error                    | Cause                   | Solution                                  |
| ------------------------ | ----------------------- | ----------------------------------------- |
| `branch already exists`  | Previous incomplete run | `git branch -D ${BRANCH_NAME}` then retry |
| `not a valid reference`  | develop doesn't exist   | Create develop from main                  |
| `is already checked out` | Branch in use elsewhere | Find and remove stale worktree            |

### Step 1.4: Verify Setup

```bash
# Verify worktree created
ls -la ".worktrees/${BRANCH_NAME}"

# Verify branch created
git branch | grep "${BRANCH_NAME}"

# Verify worktree is on correct branch
cd ".worktrees/${BRANCH_NAME}" && git branch --show-current
```

### Step 1.5: Report Context Switch

```
Worktree Setup Complete
─────────────────────────
Branch: protocol-0001-step-01
Location: .worktrees/protocol-0001-step-01
Base: develop (commit abc123)

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

Commit frequently within the worktree:

```bash
cd ".worktrees/${BRANCH_NAME}"

# Stage and commit
git add -A
git commit -m "Step ${STEP_NUM}: [description of change]"
```

**Commit message format:**

```
Step {NN}: {Brief description}

- Change 1
- Change 2

Part of protocol-{NNNN}
```

### Running Tests

All tests run in worktree context:

```bash
cd ".worktrees/${BRANCH_NAME}"

# Run tests (project-specific command)
npm test        # Node.js
pytest          # Python
go test ./...   # Go
```

---

## Phase 2.5: Approval and Deferred Merge

After step completion (`[x]`), the worktree enters an **approval phase** before merge.

### Approval Flow

```
Step Complete [x]
       │
       ▼
┌─────────────────┐
│  Code Review    │◄─────────┐
└────────┬────────┘          │
         │                   │
    ┌────┴────┐              │
    ▼         ▼              │
 PASSED    CHANGES      (fix + commit)
    │      REQUESTED ────────┘
    │
    ▼
Approved [✓]
(worktree preserved)
    │
    ▼
User Decision:
├─► [merge]  → Phase 3
├─► [wait]   → Keep worktree, continue to next step
└─► [review] → Another review cycle
```

### Why Deferred Merge?

| Problem                              | Solution                  |
| ------------------------------------ | ------------------------- |
| Review finds issues after "complete" | Fix in preserved worktree |
| User wants additional changes        | Worktree still available  |
| Multiple review iterations needed    | No merge until approved   |
| Batch merging preferred              | Accumulate approved steps |

### Managing Multiple Approved Worktrees

When multiple steps are approved but not merged:

```bash
# List all worktrees
git worktree list

# Example output:
# /project                          abc123 [develop]
# /project/.worktrees/protocol-0001-step-01  def456 [protocol-0001-step-01]  # [✓]
# /project/.worktrees/protocol-0001-step-02  ghi789 [protocol-0001-step-02]  # [✓]
```

**Merge order:** Always merge in step order to minimize conflicts.

### Returning to Approved Worktree

To make additional changes to an approved step:

```bash
cd ".worktrees/${BRANCH_NAME}"

# Make changes
# ...

# Commit
git add -A
git commit -m "Step ${STEP_NUM}: Additional changes after review"

# Status returns to [x] Complete, needs re-review
```

Update status in protocol:

```markdown
-   [x] Step 3: API Migration # Was [✓], now needs re-review
```

---

## Phase 3: Merge and Cleanup

**Called only after explicit merge approval** (process-protocol.md Step 5.6).

### Step 3.1: Final Verification in Worktree

Before merging, verify in worktree:

```bash
cd ".worktrees/${BRANCH_NAME}"

# Ensure all changes committed
git status  # Should be clean

# Run full test suite
npm test  # or project-specific command

# Run lint/types
npm run lint && npm run typecheck
```

**DO NOT proceed if:**

-   Uncommitted changes exist
-   Tests fail
-   Lint errors present

### Step 3.2: Update from Develop (Rebase)

Ensure branch is up-to-date with develop:

```bash
cd ".worktrees/${BRANCH_NAME}"

# Fetch latest
git fetch origin develop

# Rebase onto develop
git rebase develop
```

**On rebase conflict:**

1. Resolve conflicts in worktree
2. `git add .`
3. `git rebase --continue`
4. Re-run tests after rebase

If conflicts are complex, see [Conflict Resolution](#conflict-resolution).

### Step 3.3: Merge to Develop

Return to main checkout and merge:

```bash
# Return to main checkout
cd /path/to/project

# Ensure on develop
git checkout develop

# Pull latest (if using remote)
git pull origin develop

# Merge with no-ff for clear history
git merge --no-ff "${BRANCH_NAME}" -m "Merge protocol-${PROTOCOL_NUM} step ${STEP_NUM}: ${STEP_NAME}"
```

**Merge commit message format:**

```
Merge protocol-{NNNN} step {MM}: {Step Title}

Implements:
- [Key change 1]
- [Key change 2]

Protocol: {NNNN}-{protocol-name}
Step: {MM}/{TOTAL}
```

### Step 3.4: Verify Merge

```bash
# Verify merge commit
git log -1 --oneline

# Run tests on develop
npm test

# Verify no regressions
```

**If tests fail after merge:**

1. DO NOT push
2. `git reset --hard HEAD~1` to undo merge
3. Return to worktree, investigate
4. Fix and retry merge

### Step 3.5: Cleanup Worktree

After successful merge:

```bash
# Remove worktree
git worktree remove ".worktrees/${BRANCH_NAME}"

# Delete branch (now merged)
git branch -d "${BRANCH_NAME}"
```

### Step 3.6: Report Completion

```
Merge Complete
─────────────────────────
Branch: protocol-0001-step-01 → develop
Merge commit: def456
Tests: PASS

Worktree removed.
Branch deleted.

Ready for next step.
```

---

## Conflict Resolution

### During Rebase

```bash
# View conflicts
git status

# For each conflicted file:
# 1. Open file, find conflict markers
# 2. Resolve manually or with AI assistance
# 3. Stage resolved file
git add <resolved-file>

# Continue rebase
git rebase --continue
```

### Complex Conflicts

If conflicts involve significant logic changes:

1. **Document the conflict:**

    ```
    Conflict in: src/api/users.ts
    Our change: Added validation
    Their change: Refactored to async
    ```

2. **Analyze both changes:**

    - Read the full diff for both sides
    - Understand intent of each change

3. **Resolve preserving both intents:**

    - Apply our validation to their refactored code
    - Or vice versa

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
# Just remove the worktree
git worktree remove --force ".worktrees/${BRANCH_NAME}"
git branch -D "${BRANCH_NAME}"
```

### Rollback After Merge

```bash
# On develop, revert the merge commit
git revert -m 1 <merge-commit-hash>
```

---

## Error Recovery

### Stale Worktree

```
fatal: '.worktrees/protocol-0001-step-01' is a missing but locked worktree
```

**Solution:**

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
# Force remove
git worktree remove --force ".worktrees/${BRANCH_NAME}"

# Recreate
git worktree add ".worktrees/${BRANCH_NAME}" -b "${BRANCH_NAME}" develop
```

---

## Best Practices

### DO

-   Commit frequently in worktree
-   Run tests before merge
-   Use descriptive commit messages
-   Keep steps small and focused
-   Clean up worktrees after merge

### DON'T

-   Work directly on develop
-   Leave worktrees after merge
-   Skip rebase before merge
-   Ignore test failures
-   Force push to shared branches

---

## Quick Reference

### Setup

```bash
BRANCH="protocol-0001-step-01"
mkdir -p .worktrees
git worktree add ".worktrees/${BRANCH}" -b "${BRANCH}" develop
```

### Work

```bash
cd ".worktrees/${BRANCH}"
# ... make changes ...
git add -A && git commit -m "Step 01: description"
```

### Merge

```bash
cd /project
git checkout develop
git merge --no-ff "${BRANCH}" -m "Merge ${BRANCH}"
```

### Cleanup

```bash
git worktree remove ".worktrees/${BRANCH}"
git branch -d "${BRANCH}"
```

---

## Related Documentation

-   [Process Protocol](./process-protocol.md) - Protocol execution workflow
-   [Development Workflow](./development-workflow.md) - Task implementation workflow
-   [Testing Workflow](./testing-workflow.md) - Quality verification
