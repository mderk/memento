# Development Workflow (MANDATORY)

This workflow defines the STRICT order of operations for ALL development tasks.
You MUST follow this order. Skipping steps is PROHIBITED.

---

## Overview

This is the mandatory workflow for any code changes.
It ensures consistent quality through:

- Memory Bank consultation BEFORE code exploration
- Sub-agent delegation to preserve main context
- Automatic QA cycles (lint, tests, code review)

**Applies to**: Bug fixes, features, refactoring, any code changes

---

## Phase 0: Task Classification (ALWAYS FIRST)

Before ANY code exploration, classify the task.

### Step 0.1: Identify Task Type

Answer these questions:

| Question       | Options                                                            |
| -------------- | ------------------------------------------------------------------ |
| **Scope**      | backend / frontend / fullstack                                     |
| **Type**       | bug / feature / refactor / documentation                           |
| **Complexity** | trivial (1-3 lines) / simple (one file) / complex (multiple files) |

### Step 0.2: Read Memory Bank Index

Based on task type, read the relevant index FIRST:

| Task Scope | Required Reading                                      |
| ---------- | ----------------------------------------------------- |
| Backend    | `.memory_bank/guides/backend.md` (relevant sections)  |
| Frontend   | `.memory_bank/guides/frontend.md` (relevant sections) |
| Fullstack  | Both guides (relevant sections)                       |
| Bug        | `.memory_bank/workflows/bug-fix-workflow.md`          |
| Feature    | `.memory_bank/workflows/feature-workflow.md`          |
| API work   | `.memory_bank/patterns/api-design.md`                 |
| Testing    | `.memory_bank/guides/testing.md`                      |

**IMPORTANT**: Read ONLY the relevant sections, not the entire file.
Use the index files (`guides/index.md`, `workflows/index.md`) to navigate.

### Step 0.3: State Your Context

Before proceeding, explicitly state:

```
Task Classification:
- Scope: [backend/frontend/fullstack]
- Type: [bug/feature/refactor]
- Complexity: [trivial/simple/complex]

Memory Bank Read:
- File: [path to file read]
- Section: [specific section]
- Applicable patterns: [list patterns]
```

**If you cannot fill this out → You skipped Phase 0. Go back.**

---

## Phase 1: Context Exploration (AFTER Memory Bank)

### Step 1.1: Delegate to @Explore Sub-Agent

Use the @Explore sub-agent to find relevant code context.
**DO NOT search codebase directly from main agent.**

Benefits:

- Preserves main agent context for implementation
- Gets structured results with file paths
- More thorough exploration

Example prompt:

```
Find all files related to [feature/component/module].
Focus on: [specific aspect - data flow, API endpoints, components]
Return: file paths, key functions, dependencies
```

### Step 1.2: Review @Explore Results

From the results, identify:

- [ ] Files to modify
- [ ] Files to reference (dependencies)
- [ ] Existing patterns to follow
- [ ] Tests that need updating

---

## Phase 2: Planning

### Step 2.1: Create Task List

Use TodoWrite to create a structured task list.

**For trivial tasks** (1-3 lines, single obvious change):

- Skip to Phase 3 directly
- Still run lint/tests after

**For simple tasks** (one file, clear implementation):

- 2-3 todo items
- One implementation unit

**For complex tasks** (multiple files, dependencies):

- Break into minimal units of work
- Each unit should be independently testable
- Order by dependencies
- 4+ todo items

### Step 2.2: Validate Plan Against Memory Bank

Ensure your plan follows:

- [ ] Patterns from Memory Bank guides
- [ ] Existing code conventions (from @Explore results)
- [ ] Dependency order (modify dependencies before dependents)

---

## Phase 3: Implementation Loop (PER UNIT)

Repeat this phase for EACH unit of work in your task list.

### Step 3.1: Implement ONE Unit

- Make minimal, focused changes
- Follow patterns identified in Phase 0
- Mark unit as `in_progress` in TodoWrite

### Step 3.2: Lint/Type Check (MANDATORY)

Run lint and type checks on modified files.

**Project-specific commands:** See `.memory_bank/guides/testing.md` for current lint/type commands.

**LOOP**: If errors found:

1. Fix the errors
2. Re-run lint/types
3. Repeat until green

**No user confirmation needed** - iterate automatically.

### Step 3.3: Run Tests (MANDATORY)

Invoke @test-runner sub-agent:

```
Run tests for: [affected modules/files]
Include: unit tests, integration tests if applicable
```

**LOOP**: If tests fail:

1. Analyze failure
2. Fix the issue
3. Re-run tests
4. Repeat until green

**No user confirmation needed** - iterate automatically.

### Step 3.4: Mark Unit Complete

Only after:

- [ ] Lint passes
- [ ] Types pass
- [ ] Tests pass

Update TodoWrite to mark unit as `completed`.

### Step 3.5: Continue to Next Unit

If more units remain:

- Go to Step 3.1 for next unit
- Each unit gets its own lint/test cycle

---

## Phase 4: Code Review (AFTER ALL UNITS)

### Step 4.1: Invoke Code Review (MANDATORY)

Use @code-reviewer sub-agent on all modified files:

```
Review files: [list all modified files]
Focus: code quality, security, patterns, performance
```

### Step 4.2: Address Review Findings

| Severity       | Action                                   |
| -------------- | ---------------------------------------- |
| `[CRITICAL]`   | Fix immediately, must re-run review      |
| `[REQUIRED]`   | Fix before completion                    |
| `[SUGGESTION]` | Fix OR ask user if ambiguous/conflicting |

**Automatic iteration rules:**

- Fix `[CRITICAL]` and `[REQUIRED]` without asking
- Re-run @code-reviewer after fixes
- Maximum 3 review iterations, then ask user

**Ask user ONLY when:**

- Multiple valid approaches exist (genuinely ambiguous)
- Suggestions conflict with each other
- Suggestion requires significant architectural change

### Step 4.3: Re-Run Review

After fixing issues:

1. Run @code-reviewer again
2. Verify no new `[CRITICAL]` or `[REQUIRED]`
3. Repeat until clean

---

## Phase 5: Completion

### Step 5.1: Final Verification Checklist

- [ ] All TodoWrite items marked `completed`
- [ ] Lint: green
- [ ] Types: green
- [ ] Tests: green
- [ ] Code review: no `[CRITICAL]` or `[REQUIRED]` remaining
- [ ] Documentation updated (if API/interface changed)

### Step 5.2: Report to User

Provide summary:

```
## Implementation Complete

### Changes Made
- [file1]: [what changed]
- [file2]: [what changed]

### Tests
- Added/Modified: [test files]
- All passing: Yes/No

### Code Review
- Status: Clean / [N] suggestions remaining
- Remaining suggestions: [list if any]

### Next Steps
- [any follow-up tasks or considerations]
```

---

## Violation Detection

### Self-Check: Am I Following the Workflow?

**STOP immediately if you catch yourself:**

| Violation                                         | Correction                          |
| ------------------------------------------------- | ----------------------------------- |
| Searching codebase BEFORE reading Memory Bank     | Go back to Phase 0                  |
| Running Grep/Glob directly instead of @Explore    | Delegate to @Explore                |
| Implementing multiple units without testing       | Stop, run tests for completed units |
| Skipping @test-runner                             | Run tests now                       |
| Marking complete before tests pass                | Tests are MANDATORY                 |
| Fixing [SUGGESTION] without asking when ambiguous | Ask user first                      |

### Recovery

If you violated the workflow:

1. STOP current action
2. State: "Workflow violation detected: [what happened]"
3. Go back to appropriate phase
4. Continue from there

---

## Quick Reference Checklist

```
[ ] Phase 0: Classify task
    [ ] Identify scope/type/complexity
    [ ] Read Memory Bank (specific sections)
    [ ] State context explicitly

[ ] Phase 1: Explore
    [ ] Delegate to @Explore sub-agent
    [ ] Identify files to modify

[ ] Phase 2: Plan
    [ ] Create TodoWrite task list
    [ ] Validate against patterns

[ ] Phase 3: Implement (per unit)
    [ ] Implement ONE unit
    [ ] Lint → LOOP until green
    [ ] Test → LOOP until green
    [ ] Mark complete
    [ ] Repeat for all units

[ ] Phase 4: Review
    [ ] @code-reviewer
    [ ] Fix CRITICAL/REQUIRED
    [ ] Re-run until clean

[ ] Phase 5: Complete
    [ ] Final verification
    [ ] Report to user
```

---

## Fast Track (Trivial Tasks Only)

For tasks that meet ALL criteria:

- Change 1-3 lines of code
- Single file modification
- No logic changes (typos, formatting, simple renames)
- Location is already known

**Allowed shortcuts:**

- Skip @Explore (Phase 1)
- Skip TodoWrite planning (Phase 2)

**Still REQUIRED:**

- Phase 0: Task classification and MB read
- Phase 3.2: Lint check
- Phase 3.3: Test run (if tests exist for the file)
- Phase 5: Report to user

---

## Related Documentation

- [Agent Orchestration](./agent-orchestration.md) - Sub-agent delegation rules
- [Testing Workflow](./testing-workflow.md) - Detailed testing procedures
- [Code Review Workflow](./code-review-workflow.md) - Review process details
