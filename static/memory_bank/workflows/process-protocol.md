# Process Protocol Workflow

## Goal

Execute protocol steps systematically in isolated git worktrees with quality checks and progress tracking.

## When to Use

- After creating a protocol
- To implement complex features step by step
- To resume work on a multi-session feature

## Architecture

Each protocol step executes in an isolated git worktree:

```
Protocol Execution Flow
───────────────────────────────────────────────
Load Step → Setup Worktree → Execute → Merge → Cleanup
              │                │         │
              │                │         └─► develop
              │                └─► .worktrees/protocol-N-step-M/
              └─► branch: protocol-N-step-M
```

**Benefits:**
- Step failures don't affect main checkout
- Clean merge history (one merge per step)
- Easy rollback (delete worktree)
- Parallel execution ready (future)

## Process

### Step 1: Load Protocol

```bash
/prime
# Read protocol plan.md
```

From plan.md extract ONLY:
- Protocol status
- Which step is next (first `[ ]` or `[~]`)

**DO NOT read step files yet.** Just identify the next step number.

### Step 2: Load Current Step

Read ONLY the current step file (e.g., `01-container-setup.md`).

**DO NOT read other step files.** Context will be gathered by @Explore.

Identify the first pending subtask (`- [ ]` or `- [~]`).

### Step 2.5: Setup Worktree

Before executing subtasks, isolate work in a dedicated worktree.

**Follow [Git Worktree Workflow](./git-worktree-workflow.md) Phase 1.**

Quick reference:

```bash
PROTOCOL_NUM="0001"  # From protocol directory name
STEP_NUM="01"        # From step file name
BRANCH_NAME="protocol-${PROTOCOL_NUM}-step-${STEP_NUM}"

# Create worktree
mkdir -p .worktrees
git worktree add ".worktrees/${BRANCH_NAME}" -b "${BRANCH_NAME}" develop
```

**If worktree already exists:**

| Situation | Action |
|-----------|--------|
| Step in progress (`[~]`) | Resume in existing worktree |
| Step complete but worktree exists | Run cleanup (Step 5.5) |
| Unknown state | Ask user: resume or recreate |

**Report context switch:**
```
Worktree Setup Complete
─────────────────────────
Branch: protocol-0001-step-01
Location: .worktrees/protocol-0001-step-01
Base: develop

All changes will be made in this worktree.
```

**All subsequent work (Step 3, 4, 5) happens in the worktree directory.**

### Step 3: Execute Subtask

For each subtask:

1. Mark subtask `[~]` in step file
2. Follow `.memory_bank/workflows/development-workflow.md` for this subtask
3. When you see "**Development workflow complete.**" → return here
4. Mark subtask `[x]`, proceed to next subtask

Repeat until all subtasks complete.

### Step 4: Validate Step Completion

Before marking step complete, verify:

| Check                     | Method            | Action if Failed      |
| ------------------------- | ----------------- | --------------------- |
| All subtasks marked `[x]` | Parse step file   | Do not mark complete  |
| Tests passed (per result) | Check return data | Mark blocked, surface |
| No [BLOCKER] from review  | Check return data | Mark blocked, surface |

**Validation pseudocode**:

```
subtasks = parse_step_file(step)
all_complete = all(s.status == "complete" for s in subtasks)
tests_passed = result.tests_passed == true

if all_complete and tests_passed:
    mark_step_complete()
else:
    log_discrepancy()
    surface_to_user()
```

### Step 5: Mark Step Complete

Update step status in worktree:

```markdown
**Status**: Complete
**Actual**: 3 hours
```

Update protocol plan.md in worktree:

```markdown
- [x] Step 3: API Migration
```

**Commit all changes in worktree before proceeding to review.**

### Step 5.5: Code Review and Approval

**IMPORTANT:** Worktree is preserved until explicit merge approval.

#### 5.5.1: Run Code Review

Invoke @code-reviewer on all modified files in worktree:

```bash
cd ".worktrees/${BRANCH_NAME}"
# Review all changed files
```

#### 5.5.2: Handle Review Results

| Review Result | Action |
|---------------|--------|
| No BLOCKER/REQUIRED | Proceed to 5.5.3 |
| Has BLOCKER/REQUIRED | Fix in worktree, commit, re-review |
| Has SUGGESTION | Apply or document reason to skip |

**Review iteration loop:**
```
Review → Fix → Commit → Re-review → ... → Clean review
```

#### 5.5.3: Mark Approved

After clean code review (no BLOCKER/REQUIRED):

Update protocol plan.md in worktree:

```markdown
- [✓] Step 3: API Migration
```

**Worktree is preserved.** User can still request additional review iterations.

#### 5.5.4: Request Merge Confirmation

**Ask user explicitly:**

```
Step 3 Complete and Approved
─────────────────────────────
Status: [✓] Approved
Worktree: .worktrees/protocol-0001-step-03
Branch: protocol-0001-step-03

Code review: PASSED
Tests: PASSED

Ready to merge to develop?

Options:
1. [merge] - Merge now and cleanup worktree
2. [wait]  - Keep worktree, merge later
3. [review] - Run another code review iteration
```

| User Response | Action |
|---------------|--------|
| merge | Proceed to Step 5.6 |
| wait | Keep worktree, move to Step 6 (next step or pause) |
| review | Return to 5.5.1 for another review cycle |

**Default if no response:** wait (preserve worktree)

### Step 5.6: Merge and Cleanup

**Only executed after explicit merge confirmation.**

**Follow [Git Worktree Workflow](./git-worktree-workflow.md) Phase 3.**

#### 5.6.1: Final Verification

In worktree, ensure:

```bash
cd ".worktrees/${BRANCH_NAME}"

# All changes committed
git status  # Must be clean

# Tests pass
npm test  # or project-specific command

# Lint/types pass
npm run lint && npm run typecheck
```

**DO NOT proceed if any check fails.**

#### 5.6.2: Rebase onto Develop

```bash
cd ".worktrees/${BRANCH_NAME}"
git fetch origin develop
git rebase develop
```

**On conflict:** Resolve, `git add .`, `git rebase --continue`, re-run tests.

#### 5.6.3: Merge to Develop

```bash
# Return to main checkout
cd /path/to/project

# Merge with no-ff
git checkout develop
git merge --no-ff "${BRANCH_NAME}" -m "Merge protocol-${PROTOCOL_NUM} step ${STEP_NUM}: ${STEP_NAME}"

# Verify tests pass on develop
npm test
```

**If tests fail after merge:**
1. `git reset --hard HEAD~1` (undo merge)
2. Return to worktree, investigate
3. Fix and retry

#### 5.6.4: Cleanup and Update Status

```bash
git worktree remove ".worktrees/${BRANCH_NAME}"
git branch -d "${BRANCH_NAME}"
```

Update protocol plan.md (in main checkout now):

```markdown
- [M] Step 3: API Migration
```

#### 5.6.5: Report Merge

```
Merge Complete
─────────────────────────
Branch: protocol-0001-step-03 → develop
Merge commit: abc123
Tests: PASS

Worktree removed.
Status: [M] Merged

Ready for next step.
```

### Step 6: Proceed or Pause

If continuing:

- Move to next step
- Repeat process

If pausing:

- Update all status markers
- Document where you stopped
- Note any issues or decisions

## Command

```bash
# Process next step
/process-protocol .protocols/0001-feature/

# Process specific step
/process-protocol .protocols/0001-feature/ --step 3
```

The AI will:

1. Load protocol state
2. Identify current step
3. Execute tasks
4. Run verification
5. Update progress
6. Report status

## Status Markers

### Subtask Level (in step file)

| Marker  | Meaning     | Set By                                     |
| ------- | ----------- | ------------------------------------------ |
| `- [ ]` | Pending     | create-protocol                            |
| `- [~]` | In Progress | process-protocol (before delegation)       |
| `- [x]` | Complete    | process-protocol (after successful return) |
| `- [-]` | Blocked     | process-protocol (after failed return)     |

### Step Level (in plan.md)

| Marker | Meaning                                          |
| ------ | ------------------------------------------------ |
| `[ ]`  | Not Started (no subtasks touched)                |
| `[~]`  | In Progress (some subtasks done)                 |
| `[x]`  | Complete (all subtasks done, tests pass)         |
| `[✓]`  | Approved (code review passed, ready to merge)    |
| `[M]`  | Merged (changes merged to develop, worktree removed) |
| `[-]`  | Blocked (subtask blocked, awaiting fix)          |

**Step Status Flow:**
```
[ ] → [~] → [x] → [✓] → [M]
              │     │
              │     └─► (review iteration) → [x] → [✓]
              │
              └─► [-] (blocked)
```

### Protocol Level (in plan.md header)

| Status      | Meaning                            |
| ----------- | ---------------------------------- |
| Draft       | Created, not started               |
| In Progress | At least one step started          |
| Review      | All steps complete, pending merges |
| Complete    | All steps merged                   |
| Blocked     | Step blocked, awaiting action      |

## Model Strategy

| Role                      | Model | Rationale                    |
| ------------------------- | ----- | ---------------------------- |
| Orchestrator (main agent) | Opus  | Protocol state, decisions    |

The orchestrator manages protocol state and executes subtasks following development-workflow.md. Sub-agent usage is defined in development-workflow.md.

## Example Session

**Loading protocol:**

```
Protocol: PostgreSQL Migration
Status: In Progress
Progress: 2/6 steps complete (1 merged, 1 approved pending merge)

Next step: 03-api-route-migration.md
```

**Setting up worktree:**

```
Worktree Setup Complete
─────────────────────────
Branch: protocol-0001-step-03
Location: .worktrees/protocol-0001-step-03
Base: develop (commit abc123)

Loading step details...

## Step 3: API Route Migration

Tasks:
- [ ] Update users API to use Prisma
- [ ] Update products API to use Prisma
- [ ] Update orders API to use Prisma
- [ ] Update payments API to use Prisma

Starting first task in worktree...
```

**During execution (in worktree):**

```
[.worktrees/protocol-0001-step-03]

Updating users API route...

Changed:
- Import prisma from @/lib/prisma
- Replace mongoose queries with Prisma
- Update organization scoping

Committing: "Step 03: Update users API to Prisma"

Verifying:
- Lint: PASS
- Types: PASS

Task complete. Moving to products API...
```

**After subtasks complete (code review):**

```
All subtasks complete for Step 3.
Status: [x] Complete

Running code review...

Code Review Results:
- [REQUIRED] Add error handling for Prisma connection
- [SUGGESTION] Consider using transactions

Fixing REQUIRED issues...
Committing: "Step 03: Add Prisma error handling"

Re-running code review...

Code Review Results:
- [SUGGESTION] Consider using transactions

No BLOCKER or REQUIRED remaining.
Status: [✓] Approved
```

**Merge confirmation (user decision point):**

```
Step 3 Complete and Approved
─────────────────────────────
Status: [✓] Approved
Worktree: .worktrees/protocol-0001-step-03
Branch: protocol-0001-step-03

Code review: PASSED (1 suggestion remaining)
Tests: PASSED

Ready to merge to develop?

Options:
1. [merge] - Merge now and cleanup worktree
2. [wait]  - Keep worktree, merge later
3. [review] - Run another code review iteration
```

**User chooses "wait":**

```
Worktree preserved: .worktrees/protocol-0001-step-03
Status: [✓] Approved (pending merge)

You can:
- Continue to next step (worktree remains)
- Run /merge-step 03 later to merge
- Make additional changes and re-review

Protocol Progress: 3/6 steps
- Step 1: [M] Merged
- Step 2: [✓] Approved (pending merge)
- Step 3: [✓] Approved (pending merge)
- Step 4-6: [ ] Not started

Continue to next step? (y/n)
```

**Later: User merges approved steps:**

```
> /merge-step 02

Merging Step 2...
Rebasing onto develop... OK
Merging to develop... OK

Merge Complete
─────────────────────────
Branch: protocol-0001-step-02 → develop
Merge commit: def456
Tests: PASS

Worktree removed.
Status: [M] Merged

> /merge-step 03

Merging Step 3...
Rebasing onto develop... OK
Merging to develop... OK

Merge Complete
─────────────────────────
Branch: protocol-0001-step-03 → develop
Merge commit: ghi789
Tests: PASS

Worktree removed.
Status: [M] Merged

Protocol Progress: 3/6 steps merged
```

## Handling Issues

### Blocker in Current Step

1. Document the blocker
2. Mark step as blocked: `[-]`
3. Skip to next unblocked step (if independent)
4. Return when blocker resolved

### Task Failure

1. Document failure and error
2. Attempt fix
3. If not fixable, escalate
4. Don't proceed until resolved

### Scope Change

1. Update protocol ADR with new context
2. Add/modify steps as needed
3. Update estimates
4. Continue execution

## Quality Gates

After each step:

- [ ] All subtasks complete
- [ ] Tests pass
- [ ] Lint/types pass
- [ ] Code reviewed (for significant changes)

After protocol complete:

- [ ] Full test suite passes
- [ ] Production build succeeds
- [ ] Feature verified end-to-end
- [ ] Memory Bank updated (see below)
- [ ] Protocol marked complete

## Protocol Completion

When all steps are complete:

### 1. Verify All Steps Complete

Check plan.md: all steps marked `[x]`.

### 2. Update Memory Bank

Follow [Update Memory Bank](./update-memory-bank.md) workflow:

1. Collect "Memory Bank Impact" sections from all step files
2. Map impact items to Memory Bank files
3. Apply updates following the workflow
4. Validate links

### 3. Mark Protocol Complete

```markdown
**Status**: Complete
```

## Best Practices

### DO

- Complete one step fully before moving on
- Run verification after each step
- Update progress regularly
- Commit frequently in worktree
- Document decisions made during implementation
- Clean up worktrees after successful merge
- Rebase onto develop before merging

### DON'T

- Skip verification
- Work on multiple steps simultaneously
- Leave steps partially complete
- Forget to update status
- Ignore test failures
- Work directly on develop (use worktree)
- Leave worktrees after merge
- Force push to shared branches

## Related Documentation

- [Git Worktree Workflow](./git-worktree-workflow.md) - Worktree setup, merge, cleanup
- [Create Protocol](./create-protocol.md) - Create new protocols
- [Development Workflow](./development-workflow.md) - MANDATORY for all tasks
- [Testing Workflow](./testing-workflow.md) - Quality checks
- [Update Memory Bank](./update-memory-bank.md) - Documentation update process
