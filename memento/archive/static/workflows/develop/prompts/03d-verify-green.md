# Verify Green (All Tests Pass)

Run the full test suite for affected modules and verify everything passes.

## Instructions

1. Run lint/type checks on all files modified during implementation
2. Run the full test suite (not just new tests — check for regressions)
3. After all tests pass, check coverage on changed files (via `git diff --name-only` + coverage report). Changed files must have 100% line coverage. Report any uncovered lines in your output.
4. Report the status:
   - **green**: All tests pass, lint clean (success — unit is complete)
   - **red**: Some tests fail (need fixes)
   - **error**: Execution problems (need investigation)

## Output

Respond with a JSON object matching the output schema with:
- status: green/red/error
- failures: list of failing test names (if any)
- errors: list of error messages (if any)
