# Development Workflow (MANDATORY)

## STOP — Execute, Don't Just Read

**This is not documentation. This is a sequence of actions to perform.**

1. **Phase 0**: Classify task → read Memory Bank sections
2. **Phase 1**: Invoke `@Explore` sub-agent for context
3. **Phase 2**: Create plan with TodoWrite
4. **Phase 3**: Write tests first → verify red → implement → verify green (TDD)
5. **Phase 4**: Run `/code-review` (parallel competency checks)
6. **Phase 5**: Report completion

**DO NOT search/implement directly. USE SUB-AGENTS.**

Now execute Phase 0 below ↓

---

## Mode

**Standalone** (default): Full workflow, all phases.

**Protocol**:

-   Phase 1: If caller provides protocol dir + step path, load shared context before exploration:
    ```
    /load-context <protocol-dir> <step-path>
    ```
-   Phase 2: Task list is pre-defined by caller (TodoWrite only if further breakdown needed)
-   Phase 4: Skip (review done separately by caller)
-   Phase 5: Skip Memory Bank update and user report. Return: modified files list + any discoveries noted during Phase 3.

---

## Overview

This is the mandatory workflow for any code changes.
It ensures consistent quality through:

-   Memory Bank consultation BEFORE code exploration
-   Sub-agent delegation to preserve main context
-   Automatic QA cycles (lint, tests, code review)

**Applies to**: Bug fixes, features, refactoring, any code changes

---

## Workflow Diagram

```
                    ┌─────────────────────┐
                    │  PHASE 0: CLASSIFY  │
                    │  scope/type/complexity
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Trivial task?     │
                    └──────────┬──────────┘
                         YES   │   NO
                    ┌──────────┴──────────┐
                    ▼                      ▼
             ┌────────────┐    ┌─────────────────────┐
             │ FAST TRACK │    │  PHASE 1: EXPLORE   │
             │ Implement  │    │  @Explore agent     │
             │ Lint/Test  │    └──────────┬──────────┘
             │ Report     │               │
             └────────────┘    ┌──────────▼──────────┐
                               │  PHASE 2: PLAN      │
                               │  TodoWrite tasks    │
                               └──────────┬──────────┘
                                          │
                               ┌──────────▼──────────┐
                               │ PHASE 3: IMPLEMENT  │
                               │ Per unit (TDD):     │
                               │  → @Developer tests │
                               │  → Verify RED       │
                               │  → @Developer code  │
                               │  → Lint (loop)      │
                               │  → @test-runner     │
                               │  → Mark complete    │
                               └──────────┬──────────┘
                                          │
                               ┌──────────▼──────────┐
                               │  PHASE 4: REVIEW    │
                               │  /code-review       │
                               │  Fix → Re-review    │
                               └──────────┬──────────┘
                                          │
                               ┌──────────▼──────────┐
                               │  PHASE 5: COMPLETE  │
                               │  Checklist → Report │
                               └─────────────────────┘
```

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

### Step 0.1b: Route by Complexity

**If task is trivial** (meets ALL criteria):

-   1-3 lines of code
-   Single file
-   No logic changes (typos, formatting, simple renames)
-   Location already known

→ **Go to Fast Track** (below)

**Otherwise** → Continue to Step 0.2

---

## Fast Track (Trivial Tasks Only)

For tasks that meet ALL criteria:

-   Change 1-3 lines of code
-   Single file modification
-   No logic changes (typos, formatting, simple renames)
-   Location is already known

**Allowed shortcuts:**

-   Skip @Explore (Phase 1)
-   Skip TodoWrite planning (Phase 2)

**Still REQUIRED:**

-   Phase 0: Task classification and MB read
-   Phase 3.2: Lint check
-   Phase 3.3: Test run (if tests exist for the file)
-   Phase 5: Report to user

→ After Fast Track implementation, go directly to Phase 5.

---

### Step 0.2: Read Memory Bank Index

Based on task type, read the relevant index FIRST:

| Task Scope | Required Reading                                      |
| ---------- | ----------------------------------------------------- |
| Backend    | `.memory_bank/guides/backend.md` (relevant sections)  |
| Frontend   | `.memory_bank/guides/frontend.md` (relevant sections) |
| Fullstack  | Both guides (relevant sections)                       |
| Bug        | `.memory_bank/workflows/bug-fixing.md`                |
| API work   | `.memory_bank/patterns/api-design.md`                 |
| Testing    | `.memory_bank/guides/testing.md`                      |

**IMPORTANT**: Read ONLY the relevant sections, not the entire file.
Use the index files (`guides/index.md`, `workflows/index.md`) to navigate.

**Finding relevant guides:**

1. Open `README.md` in Memory Bank
2. Find "Guides" section — it lists guides by topic (backend, frontend, testing, etc.)
3. Read only the sections relevant to your task type

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

**Example (bug fix)**:

```
Task Classification:
- Scope: backend
- Type: bug
- Complexity: simple (one file)

Memory Bank Read:
- File: [relevant backend guide from README.md]
- Section: Error Handling
- Applicable patterns: error response format, logging conventions
```

**Example (new feature)**:

```
Task Classification:
- Scope: fullstack
- Type: feature
- Complexity: complex (multiple files)

Memory Bank Read:
- Files: [backend guide], [frontend guide] (see README.md navigation)
- Sections: API Routes, Components
- Applicable patterns: REST conventions, form handling
```

Note: Consult `README.md` for current guide structure — it may vary by project.

**If you cannot fill this out → You skipped Phase 0. Go back.**

**✓ Before proceeding to Phase 1:**

-   [ ] Task classified (scope/type/complexity)
-   [ ] Relevant Memory Bank sections read
-   [ ] Context statement written

→ If NO to any: Complete Phase 0 before proceeding.

---

## Phase 1: Context Exploration (AFTER Memory Bank)

### Step 1.1: Delegate to @Explore Sub-Agent

Use the @Explore sub-agent to find relevant code context.
**DO NOT search codebase directly from main agent.**

Benefits:

-   Preserves main agent context for implementation
-   Gets structured results with file paths
-   More thorough exploration

**Prompt templates by task type:**

**Bug investigation:**

```
Find code related to [symptom/error].
Trace: entry point → failure point.
Return: file paths, error handling, related tests.
```

**New feature:**

```
Find existing implementation of [similar feature].
Identify: patterns used, components involved.
Return: reference files, patterns to follow, integration points.
```

**Refactoring:**

```
Find all usages of [target function/component/module].
Map: what uses it, what it depends on.
Return: impact scope, test coverage, safe modification order.
```

### Step 1.2: Review @Explore Results

From the results, identify:

-   [ ] Files to modify
-   [ ] Files to reference (dependencies)
-   [ ] Existing patterns to follow
-   [ ] Tests that need updating

**✓ Before proceeding to Phase 2:**

-   [ ] @Explore agent used (not direct Grep/Glob)
-   [ ] Files to modify identified
-   [ ] Existing patterns noted

→ If NO to any: Delegate to @Explore now.

---

## Phase 2: Planning

> **Protocol mode**: Task list is pre-defined by caller. Use TodoWrite only if a subtask needs further sub-breakdown.

### Step 2.1: Create Task List

Use TodoWrite to create a structured task list.

**For trivial tasks** (1-3 lines, single obvious change):

-   Skip to Phase 3 directly
-   Still run lint/tests after

**For simple tasks** (one file, clear implementation):

-   2-3 todo items
-   One implementation unit

**For complex tasks** (multiple files, dependencies):

-   Break into minimal units of work
-   Each unit should be independently testable
-   Order by dependencies
-   4+ todo items

**Before implementation, plan tests (TDD — tests are written BEFORE code):**

-   What behavior should this unit produce? (define expected inputs/outputs)
-   What tests need to be written or updated?
-   Is the design testable? (dependencies injectable, logic isolated)
-   For bug fixes: what test reproduces the bug?

### Step 2.2: Validate Plan Against Memory Bank

Ensure your plan follows:

-   [ ] Patterns from Memory Bank guides
-   [ ] Existing code conventions (from @Explore results)
-   [ ] Dependency order (modify dependencies before dependents)

**✓ Before proceeding to Phase 3:**

-   [ ] Task list created (TodoWrite or protocol)
-   [ ] Tasks ordered by dependency

→ If NO to any: Create task list before implementation.

---

## Phase 3: Implementation Loop — TDD (PER UNIT)

> **Protocol mode**: Note any discoveries as you work — unexpected behavior, decisions made, gotchas, reusable patterns. Include them in your completion output.

Repeat this phase for EACH unit of work in your task list.
Each unit follows the **Red-Green** TDD cycle: write failing tests first, then write code to make them pass.

**Skip test-first (steps 3.1–3.2) when:**
-   **Pure refactoring** with no behavior change — existing tests are the spec, go directly to Step 3.3
-   **Fast Track** trivial tasks — already skip most of Phase 3

### Step 3.1: Write Tests First (RED)

A unit is one task from your Phase 2 plan (TodoWrite or protocol step).

Mark unit as `in_progress` in TodoWrite, then delegate to @Developer sub-agent with **test-only** instructions:

```
Task: Write tests ONLY for [unit description]
Expected behavior: [what the code should do — inputs, outputs, side effects]
Files to test: [from @Explore results]
Patterns: [test patterns from Memory Bank - include actual content]
Test examples: [from @Explore results]

IMPORTANT: Write ONLY test files/test cases. Do NOT write production code.
```

@Developer will:

-   Write test cases that define the expected behavior
-   For **bug fixes**: write a test that reproduces the bug
-   For **features**: write tests for the expected API/behavior
-   Follow project test patterns and conventions
-   Return test files list

### Step 3.2: Verify Red (MANDATORY)

Invoke @test-runner sub-agent on the new tests:

```
Run tests for: [new/modified test files]
Expected: new tests should FAIL (code not yet written)
```

**Evaluate result:**

| Result | Action |
|--------|--------|
| New tests FAIL | Correct — tests validate real behavior. Proceed to Step 3.3 |
| New tests PASS | Investigate — either tests are trivial/wrong, or behavior already exists |
| Compilation error | Fix imports/structure in tests, re-run |

**If tests pass unexpectedly:**

1. Check if the behavior already exists (unit may be unnecessary)
2. Check if tests are actually asserting the right thing (not trivially passing)
3. If behavior exists → reassess unit, possibly skip implementation
4. If tests are wrong → fix tests, re-run until they correctly fail

### Step 3.3: Implement Code (GREEN)

Delegate to @Developer sub-agent with **implementation-only** instructions:

```
Task: Implement [unit description]
Failing tests: [list test files/names from Step 3.1]
Files to modify: [from @Explore results]
Patterns: [relevant patterns from Memory Bank - include actual content]
Code examples: [from @Explore results]

IMPORTANT: Write ONLY production code to make the failing tests pass.
Do NOT modify the test files.
```

@Developer will:

-   Write minimal production code to make tests pass
-   Follow provided patterns
-   Run lint and fix errors
-   Return modified files list

### Step 3.4: Lint/Type Check (MANDATORY)

Run lint and type checks on modified files.

**Project-specific commands based on task scope (Phase 0):**

-   See relevant backend guide (e.g., `backend-python.md`, `backend-nextjs.md`)
-   Or see `testing.md` for general test commands

**LOOP**: If errors found:

1. Fix the errors
2. Re-run lint/types
3. Repeat until green

**No user confirmation needed** - iterate automatically.

### Step 3.5: Run Tests — Verify Green (MANDATORY)

Invoke @test-runner sub-agent:

```
Run tests for: [affected modules/files]
Include: unit tests, integration tests if applicable
Expected: ALL tests pass (both new and existing)
```

**LOOP**: If tests fail:

1. Analyze failure
2. Fix the production code (not the tests — tests are the spec)
3. Re-run tests
4. Repeat until green

**No user confirmation needed** - iterate automatically.

**Verification:**

-   [ ] New tests pass (written in Step 3.1)
-   [ ] Existing tests still pass (no regressions)

### Step 3.6: Mark Unit Complete

Only after:

-   [ ] Lint passes
-   [ ] Types pass
-   [ ] All tests pass (new + existing)

Update TodoWrite to mark unit as `completed`.

### Step 3.7: Continue to Next Unit

If more units remain:

-   Go to Step 3.1 for next unit
-   Each unit gets its own Red-Green cycle

**✓ Before marking unit complete:**

-   [ ] Tests written first (Step 3.1)
-   [ ] Red verified (Step 3.2)
-   [ ] Lint passes
-   [ ] Types pass
-   [ ] All tests pass

→ If NO to any: Fix and re-run. Do not mark complete.

---

## Phase 4: Code Review (AFTER ALL UNITS)

> **Protocol mode**: Skip this phase. Go directly to Phase 5.

### Step 4.1: Invoke Code Review (MANDATORY)

Run `/code-review` on all modified files:

```
Review files: [list all modified files]
Focus: code quality, security, patterns, performance
```

### Step 4.2: Address Review Findings

| Severity       | Action                              |
| -------------- | ----------------------------------- |
| `[BLOCKER]`    | Fix immediately, must re-run review |
| `[REQUIRED]`   | Fix before completion               |
| `[SUGGESTION]` | See decision rules below            |

**Automatic iteration rules:**

-   Fix `[BLOCKER]` and `[REQUIRED]` without asking
-   Re-run `/code-review` after fixes
-   Maximum 3 review iterations, then ask user

**For `[SUGGESTION]`:**

See [Responding to Review Feedback](../guides/code-review-guidelines.md#responding-to-review-feedback) for decision rules.

**Ask user ONLY when:**

-   Multiple valid approaches exist (genuinely ambiguous)
-   Suggestions conflict with each other
-   Suggestion requires significant architectural change

### Step 4.3: Re-Run Review

After fixing issues:

1. Run `/code-review` again
2. Verify no new `[BLOCKER]` or `[REQUIRED]`
3. Repeat until clean

**✓ Before proceeding to Phase 5:**

-   [ ] `/code-review` run on all changed files
-   [ ] No [BLOCKER] or [REQUIRED] remaining

→ If NO to any: Fix issues, re-run review.

---

## Phase 5: Completion

> **Protocol mode**: Verify lint/tests only. Skip Memory Bank update, code review check, and user report. Return modified files list and any discoveries to the caller.

### Step 5.1: Final Verification Checklist

-   [ ] All TodoWrite items marked `completed`
-   [ ] Lint: green
-   [ ] Types: green
-   [ ] Tests: green
-   [ ] Code review: no `[BLOCKER]` or `[REQUIRED]` remaining (standalone mode only)
-   [ ] Memory Bank updated (if needed) - see [Update Memory Bank](./update-memory-bank.md) (standalone mode only)

### Step 5.2: Report to User (standalone mode only)

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

| Violation                                         | Correction                                     |
| ------------------------------------------------- | ---------------------------------------------- |
| Searching codebase BEFORE reading Memory Bank     | Go back to Phase 0                             |
| Running Grep/Glob directly instead of @Explore    | Delegate to @Explore                           |
| Writing production code BEFORE tests for the unit | Stop, write tests first, verify red (Step 3.1) |
| Implementing multiple units without testing       | Stop, run tests for completed units            |
| Skipping @test-runner                             | Run tests now                                  |
| Marking complete before tests pass                | Tests are MANDATORY                            |
| Modifying tests to make them pass instead of code | Tests are the spec — fix production code       |
| Fixing [SUGGESTION] without asking when ambiguous | Ask user first                                 |

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
    [ ] Route: Trivial → Fast Track, Otherwise → Continue
    [ ] Read Memory Bank (specific sections)
    [ ] State context explicitly

[ ] Phase 1: Explore
    [ ] Delegate to @Explore sub-agent
    [ ] Identify files to modify

[ ] Phase 2: Plan
    [ ] Create TodoWrite task list
    [ ] Validate against patterns

[ ] Phase 3: Implement — TDD (per unit)
    [ ] Write tests first (@Developer — tests only)
    [ ] Verify RED (new tests fail)
    [ ] Implement code (@Developer — code only)
    [ ] Lint → LOOP until green
    [ ] @test-runner → LOOP until green
    [ ] Mark complete
    [ ] Repeat for all units

[ ] Phase 4: Review
    [ ] /code-review
    [ ] Fix BLOCKER/REQUIRED
    [ ] Re-run until clean

[ ] Phase 5: Complete
    [ ] Final verification
    [ ] Report to user
```

---

## Model Strategy

| Role                       | Model  | Phase   | Rationale              |
| -------------------------- | ------ | ------- | ---------------------- |
| Main agent                 | Opus   | All     | Orchestration, context |
| @Explore (sub-agent)       | Haiku  | Phase 1 | Fast context gathering |
| @Developer (sub-agent)     | Sonnet | Phase 3 | Code writing           |
| @test-runner (sub-agent)   | Sonnet | Phase 3 | Test execution         |
| /code-review (command)     | Sonnet | Phase 4 | Parallel competency reviews |

---

## Related Documentation

-   [Agent Orchestration](./agent-orchestration.md) - Sub-agent delegation rules
-   [Testing Workflow](./testing-workflow.md) - Detailed testing procedures
-   [Code Review Workflow](./code-review-workflow.md) - Review process details
-   [Code Review Guidelines](../guides/code-review-guidelines.md) - Severity levels and response rules
-   [Update Memory Bank](./update-memory-bank.md) - Documentation update process

---

**Development workflow complete.**

---
