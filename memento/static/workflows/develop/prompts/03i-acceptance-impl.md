# Implement Acceptance Fixes (GREEN phase)

Implement minimal production code to make the newly-written acceptance tests pass.

## Test Results

{{variables.verify_acceptance_red}}

## Working Directory

All file edits must target `{{variables.workdir}}`.

## Instructions

1. Read the failing test output to understand exactly what is expected.
2. Write the minimal production code to make the failing tests pass.
3. If you spot mechanical errors in test files (import errors, typos, wrong fixture names), fix them.
   Do NOT change assertion logic or expected values.

## Constraints

- Focus on production code; only fix mechanical test errors.
- Do NOT modify test assertions or expected values.
- Follow existing project patterns.
- Minimal implementation — just enough to pass tests.
- Do NOT run tests — the workflow runs them automatically in the next step.
