# Process Protocol Workflow

## Goal

Execute protocol steps systematically with quality checks and progress tracking.

## When to Use

- After creating a protocol
- To implement complex features step by step
- To resume work on a multi-session feature

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

Update step status:

```markdown
**Status**: Complete
**Actual**: 3 hours
```

Update protocol plan.md:

```markdown
- [x] Step 3: API Migration
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

| Marker | Meaning                                 |
| ------ | --------------------------------------- |
| `[ ]`  | Not Started (no subtasks touched)       |
| `[~]`  | In Progress (some subtasks done)        |
| `[x]`  | Complete (all subtasks done, validated) |
| `[-]`  | Blocked (subtask blocked, awaiting fix) |

### Protocol Level (in plan.md header)

| Status      | Meaning                       |
| ----------- | ----------------------------- |
| Draft       | Created, not started          |
| In Progress | At least one step started     |
| Complete    | All steps complete            |
| Blocked     | Step blocked, awaiting action |

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
Progress: 2/6 steps complete

Next step: 03-api-route-migration.md

Loading step details...

## Step 3: API Route Migration

Tasks:
- [ ] Update users API to use Prisma
- [ ] Update products API to use Prisma
- [ ] Update orders API to use Prisma
- [ ] Update payments API to use Prisma

Starting first task...
```

**During execution:**

```
Updating users API route...

Changed:
- Import prisma from @/lib/prisma
- Replace mongoose queries with Prisma
- Update organization scoping

Verifying:
- Lint: PASS
- Types: PASS

Task complete. Moving to products API...
```

**After step completion:**

```
All tasks complete for Step 3.

Running verification:
- Unit tests: 45 passed
- E2E tests: 12 passed
- Lint: PASS
- Types: PASS

Step 3 complete!

Protocol Progress: 3/6 steps (50%)

Next step: 04-data-migration-script.md

Continue to next step? (y/n)
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
- Commit at logical points
- Document decisions made during implementation

### DON'T

- Skip verification
- Work on multiple steps simultaneously
- Leave steps partially complete
- Forget to update status
- Ignore test failures

## Related Documentation

- [Create Protocol](./create-protocol.md) - Create new protocols
- [Development Workflow](./development-workflow.md) - MANDATORY for all tasks
- [Testing Workflow](./testing-workflow.md) - Quality checks
- [Update Memory Bank](./update-memory-bank.md) - Documentation update process
