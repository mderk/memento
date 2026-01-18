# Develop Protocol Workflow

## STOP — Execute These Steps

**This is not documentation. This is a sequence of actions.**

For each subtask in the protocol step:
1. Mark subtask `[~]`
2. Execute phases 0-5 below
3. Mark subtask `[x]`
4. Repeat for next subtask

---

## Goal

Execute protocol steps with embedded development workflow. All orchestration happens here — no external workflow references.

## When to Use

- After creating a protocol
- To implement complex features step by step
- To resume work on a multi-session feature

---

## Load Protocol

```bash
/prime
# Read protocol plan.md
```

From plan.md extract ONLY:
- Protocol status
- Which step is next (first `[ ]` or `[~]`)

**DO NOT read step files yet.** Just identify the next step number.

## Load Current Step

Read ONLY the current step file (e.g., `01-container-setup.md`).

**DO NOT read other step files.** Context will be gathered by @Explore.

Identify the first pending subtask (`- [ ]` or `- [~]`).

---

## Execute Subtask (Phases 0-5)

For each subtask, execute all phases below:

### Phase 0: Classify

**Action**: Determine task scope before any exploration.

| Question       | Options                              |
| -------------- | ------------------------------------ |
| **Scope**      | backend / frontend / fullstack       |
| **Type**       | bug / feature / refactor             |
| **Complexity** | trivial / simple / complex           |

**If trivial** (1-3 lines, single file, no logic change):
- Skip Phase 1 (Explore)
- Skip Phase 2 (Plan)
- Go directly to Phase 3

**Otherwise**: Continue to Phase 1.

### Phase 1: Explore

**Action**: Invoke @Explore sub-agent.

```
@Explore (model: haiku)

Find code related to: [subtask description]
Return: file paths, existing patterns, integration points
```

From results, note:
- Files to modify
- Patterns to follow
- Dependencies

### Phase 2: Plan

**Action**: Create task breakdown with TodoWrite.

For complex subtasks, break into smaller units:
- Each unit independently testable
- Order by dependencies
- 2-4 items typical

### Phase 3: Implement

**Action**: For each unit in plan:

#### 3.1 Code with @Developer

```
@Developer (model: sonnet)

Task: [unit description]
Files: [from @Explore]
Patterns: [from Memory Bank / @Explore]
```

@Developer will:
- Make focused changes
- Follow provided patterns
- Fix lint errors
- Return modified files

#### 3.2 Lint Loop (MANDATORY)

Run lint/type checks based on scope (Phase 0).

See `.memory_bank/guides/testing.md` for project-specific commands.

**LOOP**: If errors → fix → re-run → repeat until green.

#### 3.3 Test (MANDATORY)

```
@test-runner (model: sonnet)

Run tests for: [affected modules]
```

**LOOP**: If failures → fix → re-run → repeat until green.

#### 3.4 Mark Unit Complete

Only after lint + tests pass, mark unit done in TodoWrite.

### Phase 4: Review

**Action**: Invoke code review.

```
@code-reviewer (model: opus)

Review files: [all modified files]
Focus: code quality, security, patterns
```

| Severity       | Action                    |
| -------------- | ------------------------- |
| `[BLOCKER]`    | Fix, re-run review        |
| `[REQUIRED]`   | Fix before completion     |
| `[SUGGESTION]` | Apply if clear benefit    |

**LOOP**: Fix blockers/required → re-review → repeat until clean.

### Phase 5: Complete

Subtask done. Update step file:
- Mark subtask `[x]`
- Proceed to next subtask

---

## Validate Step Completion

Before marking step complete:

| Check                     | Action if Failed      |
| ------------------------- | --------------------- |
| All subtasks marked `[x]` | Do not mark complete  |
| Tests passed              | Mark blocked, surface |
| No [BLOCKER] remaining    | Mark blocked, surface |

## Mark Step Complete

Update step file:
```markdown
**Status**: Complete
```

Update plan.md:
```markdown
- [x] Step N: Description
```

## Proceed or Pause

**If continuing**: Move to next step, repeat process.

**If pausing**:
- Update all status markers
- Document where stopped
- Note any issues

---

## Status Markers

### Subtask Level (in step file)

| Marker  | Meaning     |
| ------- | ----------- |
| `- [ ]` | Pending     |
| `- [~]` | In Progress |
| `- [x]` | Complete    |
| `- [-]` | Blocked     |

### Step Level (in plan.md)

| Marker | Meaning                           |
| ------ | --------------------------------- |
| `[ ]`  | Not Started                       |
| `[~]`  | In Progress (some subtasks done)  |
| `[x]`  | Complete (all validated)          |
| `[-]`  | Blocked                           |

---

## Model Strategy

| Role           | Model  | Phase   |
| -------------- | ------ | ------- |
| Orchestrator   | Opus   | All     |
| @Explore       | Haiku  | 1       |
| @Developer     | Sonnet | 3       |
| @test-runner   | Sonnet | 3       |
| @code-reviewer | Opus   | 4       |

---

## Quality Gates

After each step:
- [ ] All subtasks complete
- [ ] Lint/types pass
- [ ] Tests pass
- [ ] Code reviewed

After protocol complete:
- [ ] Full test suite passes
- [ ] Memory Bank updated (see [Update Memory Bank](./update-memory-bank.md))
- [ ] Protocol marked complete

---

## Related Documentation

- [Create Protocol](./create-protocol.md) - Create new protocols
- [Testing Workflow](./testing-workflow.md) - Detailed testing
- [Update Memory Bank](./update-memory-bank.md) - Documentation updates
