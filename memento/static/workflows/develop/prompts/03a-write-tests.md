# Write Tests (RED phase)

You are writing failing tests for a unit of work. These tests define the expected behavior BEFORE implementation.

## Unit

{{variables.unit}}

## Instructions

1. Read existing test files in the project to understand conventions (test framework, patterns, file organization)
2. Write test cases that define the expected behavior for this unit:
   - For **bug fixes**: write a test that reproduces the bug
   - For **features**: write tests for the expected API/behavior
   - For **refactoring** with no behavior change: verify existing tests cover the behavior, add tests only if coverage gaps exist. The verify-red step will be skipped automatically for refactors.
3. Follow the project's test patterns (AAA pattern, naming conventions, fixture usage)
4. Write ONLY test files. Do NOT write any production code.
5. Tests should FAIL when run (since production code doesn't exist yet)

## Constraints

- Do not create production code
- Do not modify existing production code
- Only create or modify test files
- Follow existing test file organization
