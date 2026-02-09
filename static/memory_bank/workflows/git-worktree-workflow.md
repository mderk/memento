# Git Worktree Workflow

## Goal

Isolate protocol execution in a dedicated git worktree for safe, reversible changes and clean merge history.

## Core Rule

**Protocol = 1 branch = 1 worktree.** All steps are commits within that worktree.

## When to Use

-   Processing protocol steps (called from process-protocol.md)
-   Any multi-step feature requiring isolation from the main checkout

## Benefits

| Benefit       | Description                          |
| ------------- | ------------------------------------ |
| Isolation     | Protocol work doesn't affect develop |
| Clean history | One merge commit per protocol        |
| Easy rollback | Delete worktree, no cleanup needed   |
| Resumable     | Worktree persists across sessions    |

## Prerequisites

-   [ ] Git repository initialized
-   [ ] `develop` branch exists and is clean
-   [ ] No uncommitted changes in main checkout

## Directory Structure

```
project/
├── .worktrees/                    # Worktree directory (gitignored)
│   └── protocol-0001/             # One worktree per protocol
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

### Step 1.1: Determine Branch Name

```bash
BRANCH="protocol-${PROTOCOL_NUM}"
```

### Step 1.2: Check Existing Worktree

```bash
git worktree list | grep "${BRANCH}"
```

If exists: protocol is being resumed. Work in the existing worktree. If state is unclear, ask user.

### Step 1.3: Create Worktree

```bash
mkdir -p .worktrees
git worktree add ".worktrees/${BRANCH}" -b "${BRANCH}" develop
```

**On error:**

| Error                    | Cause                   | Solution                             |
| ------------------------ | ----------------------- | ------------------------------------ |
| `branch already exists`  | Previous incomplete run | `git branch -D ${BRANCH}` then retry |
| `not a valid reference`  | develop doesn't exist   | Create develop from main             |
| `is already checked out` | Branch in use elsewhere | Find and remove stale worktree       |

### Step 1.4: Copy Environment Files

Worktrees don't include gitignored files. Copy `.env*` files from the main checkout:

```bash
for f in .env .env.local .env.test .env.development .env.production; do
  [ -f "$f" ] && cp "$f" ".worktrees/${BRANCH}/$f"
done
```

### Step 1.5: Verify Setup

```bash
ls -la ".worktrees/${BRANCH}"
git -C ".worktrees/${BRANCH}" branch --show-current
```

### Step 1.6: Report

```
Worktree Ready
─────────────────────────
Branch: protocol-0001
Location: .worktrees/protocol-0001
```

**All subsequent work happens in the worktree directory.**

---

## Phase 2: Working in Worktree

### Important Paths

When executing in worktree, paths are relative to worktree root:

| Resource       | Path                                |
| -------------- | ----------------------------------- |
| Source code    | `.worktrees/{branch}/src/`          |
| Tests          | `.worktrees/{branch}/tests/`        |
| Memory Bank    | `.worktrees/{branch}/.memory_bank/` |
| Protocol files | `.worktrees/{branch}/.protocols/`   |

### Committing Changes

Use `/commit` to stage and commit with a properly formatted message.

If `/commit` is unavailable, follow [Commit Message Rules](./commit-message-rules.md) manually.

### Running Tests

```bash
cd ".worktrees/${BRANCH}"
npm test        # Node.js
pytest          # Python
go test ./...   # Go
```

---

## Phase 3: Merge to Develop

Called via `/merge-protocol` after all steps are complete.

### 3.1: Final Verification

```bash
cd ".worktrees/${BRANCH}"

git status        # Must be clean
npm test          # Full test suite
npm run lint      # Lint must pass
```

**DO NOT proceed if any check fails.**

### 3.2: Code Review

Run `/code-review` on all changes vs develop:

```bash
cd ".worktrees/${BRANCH}"
git diff develop --stat
```

Review iteration loop: Review → Fix → `/commit` → Re-review → ... → Clean

### 3.3: User Confirmation

```
Protocol Ready for Merge
─────────────────────────────
Branch: protocol-0001
Changes vs develop: 15 files, +450/-120

Code review: PASSED
Tests: PASSED

Ready to merge to develop?

Options:
1. [merge]  - Merge now
2. [wait]   - Keep branch, merge later
3. [review] - Run another code review
```

### 3.4: Rebase and Merge

```bash
cd ".worktrees/${BRANCH}"
git rebase develop

cd "${PROJECT_ROOT}"
git checkout develop
git merge --no-ff "${BRANCH}" -m "feat: protocol-${PROTOCOL_NUM} — ${PROTOCOL_NAME}"
npm test  # Verify on develop
```

**If tests fail:** `git reset --hard HEAD~1`, fix in worktree, retry.

### 3.5: Cleanup

```bash
git worktree remove ".worktrees/${BRANCH}"
git branch -d "${BRANCH}"
```

---

## Conflict Resolution

### During Rebase

```bash
git status
git add <resolved-file>
git rebase --continue
```

### Complex Conflicts

1.  **Document:** which file, what each side changed
2.  **Analyze:** read full diff for both sides, understand intent
3.  **Resolve:** preserve both intents
4.  **Test:** thoroughly after resolution

### When to Escalate

Escalate to user when:

-   Conflict involves architectural decisions
-   Multiple valid resolution approaches exist
-   Changes contradict each other semantically

---

## Rollback Procedures

### Rollback Uncommitted Changes

```bash
cd ".worktrees/${BRANCH}"
git checkout -- .
git clean -fd
```

### Rollback Entire Protocol (Before Merge)

```bash
git worktree remove --force ".worktrees/${BRANCH}"
git branch -D "${BRANCH}"
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
cd ".worktrees/${BRANCH}"
git checkout "${BRANCH}"
```

### Detached HEAD

```bash
cd ".worktrees/${BRANCH}"
git checkout -B "${BRANCH}"
```

### Corrupted Worktree

```bash
git worktree remove --force ".worktrees/${BRANCH}"
git worktree add ".worktrees/${BRANCH}" -b "${BRANCH}" develop
```

---

## Best Practices

### DO

-   Commit frequently via `/commit`
-   Run tests before merge
-   Follow [Commit Message Rules](./commit-message-rules.md)
-   Keep steps small and focused

### DON'T

-   Work directly on develop
-   Leave worktrees after merge
-   Skip rebase before merge
-   Ignore test failures
-   Force push to shared branches

---

## Quick Reference

```bash
# Setup
BRANCH="protocol-0001"
mkdir -p .worktrees
git worktree add ".worktrees/${BRANCH}" -b "${BRANCH}" develop

# Work (repeat per step)
cd ".worktrees/${BRANCH}"
# ... make changes ...
/commit

# Merge (after all steps)
/merge-protocol .protocols/0001-feature/

# Or manually:
cd ".worktrees/${BRANCH}" && git rebase develop
cd "${PROJECT_ROOT}" && git checkout develop
git merge --no-ff "${BRANCH}" -m "feat: protocol-0001 — feature name"
git worktree remove ".worktrees/${BRANCH}"
git branch -d "${BRANCH}"
```

---

## Related Documentation

-   [Process Protocol](./process-protocol.md) — Protocol execution workflow
-   [Development Workflow](./development-workflow.md) — Task implementation workflow
-   [Commit Message Rules](./commit-message-rules.md) — Commit conventions
-   [Testing Workflow](./testing-workflow.md) — Quality verification
