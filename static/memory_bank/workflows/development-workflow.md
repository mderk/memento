# Development Workflow (MANDATORY)

## STOP — Execute, Don't Just Read

**This is not documentation. This is a sequence of actions to perform.**

1. **Phase 0**: Classify task → read Memory Bank sections
2. **Phase 1**: Invoke `@Explore` sub-agent for context
3. **Phase 2**: Create plan with TodoWrite
4. **Phase 3**: Invoke `@Developer` sub-agent for implementation
5. **Phase 4**: Invoke `@code-reviewer` sub-agent
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
                               │ Per unit:           │
                               │  → @Developer       │
                               │  → Lint (loop)      │
                               │  → @test-runner     │
                               │  → Mark complete    │
                               └──────────┬──────────┘
                                          │
                               ┌──────────▼──────────┐
                               │  PHASE 4: REVIEW    │
                               │  @code-reviewer     │
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
| Bug        | `.memory_bank/workflows/bug-fix-workflow.md`          |
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

**Before implementation, consider testability:**

-   How will this code be tested?
-   What tests need to be written or updated?
-   Is the design testable? (dependencies injectable, logic isolated)

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

## Phase 3: Implementation Loop (PER UNIT)

> **Protocol mode**: Note any discoveries as you work — unexpected behavior, decisions made, gotchas, reusable patterns. Include them in your completion output.

Repeat this phase for EACH unit of work in your task list.

### Step 3.1: Implement ONE Unit

A unit is one task from your Phase 2 plan (TodoWrite or protocol step).

Mark unit as `in_progress` in TodoWrite, then delegate to @Developer sub-agent:

```
Task: [unit description]
Files to modify: [from @Explore results]
Patterns: [relevant patterns from Memory Bank - include actual content]
Code examples: [from @Explore results]
```

@Developer will:

-   Make minimal, focused changes
-   Follow provided patterns
-   Write tests for new/changed functionality
-   Run lint and fix errors
-   Return modified files list

### Step 3.2: Lint/Type Check (MANDATORY)

Run lint and type checks on modified files.

**Project-specific commands based on task scope (Phase 0):**

-   See relevant backend guide (e.g., `backend-python.md`, `backend-nextjs.md`)
-   Or see `testing.md` for general test commands

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

**Verification:**

-   [ ] Existing tests pass
-   [ ] New tests added for changed code (unless pure refactor with no behavior change)

### Step 3.4: Mark Unit Complete

Only after:

-   [ ] Lint passes
-   [ ] Types pass
-   [ ] Tests pass

Update TodoWrite to mark unit as `completed`.

### Step 3.5: Continue to Next Unit

If more units remain:

-   Go to Step 3.1 for next unit
-   Each unit gets its own lint/test cycle

**✓ Before marking unit complete:**

-   [ ] Lint passes
-   [ ] Types pass
-   [ ] Tests pass

→ If NO to any: Fix and re-run. Do not mark complete.

---

## Phase 4: Code Review (AFTER ALL UNITS)

> **Protocol mode**: Skip this phase. Go directly to Phase 5.

### Step 4.1: Invoke Code Review (MANDATORY)

Use @code-reviewer sub-agent on all modified files:

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
-   Re-run @code-reviewer after fixes
-   Maximum 3 review iterations, then ask user

**For `[SUGGESTION]`:**

See [Responding to Review Feedback](../guides/code-review-guidelines.md#responding-to-review-feedback) for decision rules.

**Ask user ONLY when:**

-   Multiple valid approaches exist (genuinely ambiguous)
-   Suggestions conflict with each other
-   Suggestion requires significant architectural change

### Step 4.3: Re-Run Review

After fixing issues:

1. Run @code-reviewer again
2. Verify no new `[BLOCKER]` or `[REQUIRED]`
3. Repeat until clean

**✓ Before proceeding to Phase 5:**

-   [ ] @code-reviewer run on all changed files
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
    [ ] Route: Trivial → Fast Track, Otherwise → Continue
    [ ] Read Memory Bank (specific sections)
    [ ] State context explicitly

[ ] Phase 1: Explore
    [ ] Delegate to @Explore sub-agent
    [ ] Identify files to modify

[ ] Phase 2: Plan
    [ ] Create TodoWrite task list
    [ ] Validate against patterns

[ ] Phase 3: Implement (per unit)
    [ ] Delegate to @Developer
    [ ] Lint → LOOP until green
    [ ] @test-runner → LOOP until green
    [ ] Mark complete
    [ ] Repeat for all units

[ ] Phase 4: Review
    [ ] @code-reviewer
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
| @code-reviewer (sub-agent) | Opus   | Phase 4 | Deep code review       |

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
