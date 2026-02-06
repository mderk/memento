# Process Protocol Workflow

## Goal

Execute protocol steps systematically in isolated git worktrees with quality checks and progress tracking.

## When to Use

- After creating a protocol
- To implement complex features step by step
- To resume work on a multi-session feature

## Architecture

Each protocol step executes in an isolated git worktree. The branching strategy is configured in `plan.md` metadata.

```
branching = plan.md.branching ?? "per-protocol"
```

### per-protocol (default)

```
Load Step → Setup Worktree → Execute → Fast Merge → Cleanup
              │                │              │
              │                │              └─► protocol branch
              │                └─► .worktrees/protocol-N-step-M/
              └─► step branch from protocol branch

All steps complete → /merge-protocol → review → develop
```

### per-step

```
Load Step → Setup Worktree → Execute → Review → Approval → Merge → Cleanup
              │                │                              │
              │                │                              └─► develop
              │                └─► .worktrees/protocol-N-step-M/
              └─► step branch from develop
```

### per-group

Same as per-protocol, but with group branches instead of one protocol branch.

**Benefits:**
- Step failures don't affect main checkout or other steps
- Clean merge history
- Easy rollback (delete worktree)
- per-protocol: review entire feature at once, not piece by piece
- per-step: merge independent features immediately

## Process

### Step 1: Load Protocol

```bash
/prime
# Read protocol plan.md
```

From plan.md extract:
- Protocol status
- **Branching strategy** (`branching` field, default: `per-protocol`)
- Which step is next (first `[ ]` or `[~]`)
- Group membership (if `per-group`)

**DO NOT read step files yet.** Just identify the next step number.

### Step 2: Load Current Step

Read ONLY the current step file (e.g., `01-container-setup.md`).

**DO NOT read other step files.** Context will be gathered by @Explore.

Identify the first pending subtask (`- [ ]` or `- [~]`).

### Step 2.5: Setup Worktree

Before executing subtasks, isolate work in a dedicated worktree.

**Follow [Git Worktree Workflow](./git-worktree-workflow.md) Phase 1.**

#### Determine branch structure

```
PROTOCOL_NUM = from protocol directory name
STEP_NUM = from step file name
STRATEGY = plan.md.branching ?? "per-protocol"
STEP_BRANCH = "protocol-${PROTOCOL_NUM}-step-${STEP_NUM}"

if STRATEGY == "per-protocol":
    PARENT_BRANCH = "protocol-${PROTOCOL_NUM}"
elif STRATEGY == "per-group":
    PARENT_BRANCH = "protocol-${PROTOCOL_NUM}-group-${GROUP_NUM}"
elif STRATEGY == "per-step":
    PARENT_BRANCH = "develop"
```

#### Create parent branch (per-protocol / per-group only)

If parent branch worktree doesn't exist yet:

```bash
mkdir -p .worktrees
git worktree add ".worktrees/${PARENT_BRANCH}" -b "${PARENT_BRANCH}" develop
```

#### Create step worktree

```bash
git worktree add ".worktrees/${STEP_BRANCH}" -b "${STEP_BRANCH}" "${PARENT_BRANCH}"
```

**If worktree already exists:**

| Step Status | Action |
|-------------|--------|
| `[~]` In Progress | Resume in existing worktree |
| `[x]` Complete | Resume for review or changes |
| `[✓]` Approved (per-step) | Ready for merge, or make more changes |
| Unknown | Ask user: resume or recreate |

**Report context switch:**
```
Worktree Setup Complete
─────────────────────────
Strategy: per-protocol
Branch: protocol-0001-step-01
Parent: protocol-0001
Location: .worktrees/protocol-0001-step-01

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

**Commit all changes in worktree before proceeding to review.** Follow [Commit Message Rules](commit-message-rules.md).

### Step 5.5: Merge Step (strategy-dependent)

Behavior depends on branching strategy.

**Follow [Git Worktree Workflow](./git-worktree-workflow.md) Phase 2.5.**

---

#### Strategy: per-protocol / per-group — Fast Merge

Step merges into parent branch (protocol/group) **without review or user confirmation**.

##### 5.5.1: Verify and Merge

```bash
cd ".worktrees/${STEP_BRANCH}"

# Verify clean state and tests
git status  # Must be clean
npm test    # Must pass

# Rebase onto parent
git rebase "${PARENT_BRANCH}"

# Merge into parent (in parent worktree)
cd ".worktrees/${PARENT_BRANCH}"
git merge --no-ff "${STEP_BRANCH}" -m "feat: step ${STEP_NUM} — ${STEP_NAME}"
```

##### 5.5.2: Cleanup Step Worktree

```bash
cd /path/to/project
git worktree remove ".worktrees/${STEP_BRANCH}"
git branch -d "${STEP_BRANCH}"
```

##### 5.5.3: Update Status

Update plan.md: `- [M] Step N: Title`

##### 5.5.4: Report

```
Step Merged (fast)
─────────────────────────
Step: protocol-0001-step-01 → protocol-0001
Tests: PASS

Step worktree removed.
Protocol worktree remains: .worktrees/protocol-0001

Ready for next step.
```

**No user confirmation needed.** The protocol/group branch is the isolation boundary. Code review happens at protocol/group level via `/merge-protocol`.

→ Proceed to Step 6.

---

#### Strategy: per-step — Review + Approval

Step merges into develop **with review and user confirmation**.

##### 5.5.1: Run Code Review

Invoke @code-reviewer on all modified files in worktree:

```bash
cd ".worktrees/${STEP_BRANCH}"
# Review all changed files
```

##### 5.5.2: Handle Review Results

| Review Result | Action |
|---------------|--------|
| No BLOCKER/REQUIRED | Proceed to 5.5.3 |
| Has BLOCKER/REQUIRED | Fix in worktree, commit, re-review |
| Has SUGGESTION | Apply or document reason to skip |

**Review iteration loop:**
```
Review → Fix → Commit → Re-review → ... → Clean review
```

##### 5.5.3: Mark Approved

After clean code review (no BLOCKER/REQUIRED):

Update protocol plan.md in worktree:

```markdown
- [✓] Step 3: API Migration
```

**Worktree is preserved.** User can still request additional review iterations.

##### 5.5.4: Request Merge Confirmation

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

### Step 5.6: Merge to Develop (per-step only)

**Only executed after explicit merge confirmation. Only for `per-step` strategy.**

For `per-protocol`/`per-group`, use `/merge-protocol` after all steps complete.

**Follow [Git Worktree Workflow](./git-worktree-workflow.md) Phase 3.**

#### 5.6.1: Final Verification

```bash
cd ".worktrees/${STEP_BRANCH}"

git status        # Must be clean
npm test          # Must pass
npm run lint      # Must pass
```

**DO NOT proceed if any check fails.**

#### 5.6.2: Rebase onto Develop

```bash
cd ".worktrees/${STEP_BRANCH}"
git rebase develop
```

**On conflict:** Resolve, `git add .`, `git rebase --continue`, re-run tests.

#### 5.6.3: Merge to Develop

```bash
cd /path/to/project
git checkout develop
git merge --no-ff "${STEP_BRANCH}" -m "feat: protocol-${PROTOCOL_NUM} step ${STEP_NUM} — ${STEP_NAME}"
npm test  # Verify on develop
```

**If tests fail:** `git reset --hard HEAD~1`, fix in worktree, retry.

#### 5.6.4: Cleanup and Update Status

```bash
git worktree remove ".worktrees/${STEP_BRANCH}"
git branch -d "${STEP_BRANCH}"
```

Update plan.md: `- [M] Step N: Title`

#### 5.6.5: Report

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

**Step Status Flow (per-step):**
```
[ ] → [~] → [x] → [✓] → [M]
              │     │
              │     └─► (review iteration) → [x] → [✓]
              │
              └─► [-] (blocked)
```

**Step Status Flow (per-protocol / per-group):**
```
[ ] → [~] → [x] → [M]
              │
              └─► [-] (blocked)
```

Note: `[✓]` (Approved) is only used with `per-step` strategy. With `per-protocol`/`per-group`, steps go directly from `[x]` to `[M]` via fast merge. Code review happens at protocol/group level.

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

## Example Sessions

### Example: per-protocol (default)

**Loading protocol:**

```
Protocol: PostgreSQL Migration
Strategy: per-protocol (default)
Status: In Progress
Progress: 2/6 steps merged into protocol branch

Next step: 03-api-route-migration.md
```

**Setting up worktree:**

```
Worktree Setup Complete
─────────────────────────
Strategy: per-protocol
Branch: protocol-0001-step-03
Parent: protocol-0001
Location: .worktrees/protocol-0001-step-03

Starting first task in worktree...
```

**After step completion (fast merge):**

```
All subtasks complete for Step 3.
Tests: PASS

Step Merged (fast)
─────────────────────────
Step: protocol-0001-step-03 → protocol-0001
Tests: PASS

Step worktree removed.
Protocol worktree remains: .worktrees/protocol-0001

Protocol Progress: 3/6 steps
- Step 1-3: [M] Merged into protocol branch
- Step 4-6: [ ] Not started

Continue to next step? (y/n)
```

**After all steps — protocol merge:**

```
> /merge-protocol .protocols/0001-migration/

Protocol Ready for Merge
─────────────────────────────
Branch: protocol-0001
Steps merged: 6/6
Changes vs develop: 25 files, +800/-300

Running code review...
Code review: PASSED

Ready to merge to develop?
> merge

Merging protocol-0001 → develop... OK
Tests: PASS

Protocol Complete!
Worktree removed.
```

### Example: per-step

**Loading protocol:**

```
Protocol: Platform Modernization
Strategy: per-step
Status: In Progress

Next step: 02-billing.md
```

**After step completion (review + approval):**

```
All subtasks complete for Step 2.
Status: [x] Complete

Running code review...
Code review: PASSED
Status: [✓] Approved

Step 2 Complete and Approved
─────────────────────────────
Ready to merge to develop?

Options:
1. [merge] - Merge now
2. [wait]  - Keep worktree, merge later
3. [review] - Run another review cycle

> wait

Worktree preserved. Use /merge-step 02 later.
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

### 1. Verify All Steps Merged

Check plan.md: all steps marked `[M]`.

### 2. Merge to Develop (per-protocol / per-group)

If using `per-protocol` or `per-group` strategy, the protocol/group branch must still be merged into develop:

```bash
/merge-protocol .protocols/0001-feature/
```

This triggers:
1. Code review on all changes vs develop
2. Review iteration loop
3. User confirmation
4. Rebase + merge to develop
5. Worktree cleanup

See [Git Worktree Workflow](./git-worktree-workflow.md) Phase 3 for details.

For `per-step` strategy, steps are already merged — skip this.

### 3. Update Memory Bank

Follow [Update Memory Bank](./update-memory-bank.md) workflow:

1. Collect "Memory Bank Impact" sections from all step files
2. Map impact items to Memory Bank files
3. Apply updates following the workflow
4. Validate links

### 4. Mark Protocol Complete

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
