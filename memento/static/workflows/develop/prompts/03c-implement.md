# Implement Code (GREEN phase)

Write the minimal production code to make the failing tests pass.

## Unit

{{variables.unit}}

## Task Context

{{variables.task}}

## Failing Tests

{{results.verify-red}}

## Plan

{{results.plan}}

## Instructions

1. Read the failing test files to understand exactly what behavior is expected
2. Read existing production code to understand patterns and conventions
3. Write the MINIMAL code needed to make the tests pass:
   - Follow existing code patterns (naming, structure, error handling)
   - Don't over-engineer or add features beyond what tests require
   - Don't add error handling unless tests require it
4. Run lint and type checks on all modified files. Fix any errors — iterate until clean.
   Use the project's lint/type commands from `.memory_bank/guides/testing.md` or the relevant backend/frontend guide.
5. Do NOT modify the test files — tests are the spec

## Constraints

- Write only production code
- Do not modify test files
- Follow existing project patterns
- Minimal implementation — just enough to pass tests
