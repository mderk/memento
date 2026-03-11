# Execute Tests

Run the project test suite and analyze results.

## Instructions

1. Determine the test scope:
   - If specific files/modules are provided in context, test those
   - Otherwise, run the full test suite
2. Read `.memory_bank/guides/testing.md` for project-specific test commands
3. Determine changed files via `git diff --name-only HEAD~1` (or `git diff --name-only --cached` if staged)
4. Run tests with coverage enabled:
   - pytest: `--cov=<package> --cov-report=term-missing`
   - jest/vitest: `--coverage`
   - Other frameworks: use appropriate coverage flag
5. Analyze results:
   - Count passed, failed, errors, skipped
   - Check overall coverage percentage
   - For failures: read test file, analyze stack trace, identify root cause
   - Assign priority to each failure: CRITICAL (blocks merge), REQUIRED (must fix), SUGGESTION (nice-to-have)
6. Parse per-file coverage from the coverage report output (`term-missing` for pytest, `--coverage` summary for jest):
   - Report each changed file in `coverage_details` with its coverage percentage
   - Report uncovered line numbers as strings in `missing_lines`: `"42"` for single lines, `"55-60"` for ranges
   - Changed files must have 100% line coverage
7. Escalate to user when: flaky tests, tests >10s, unmockable external deps, cannot reach 100% coverage on changed files

## Output

Structure your textual output as: Summary → Failed Tests (file:line) → Coverage (changed files) → Coverage Gaps (project-wide, narrative only).

Respond with a JSON object matching the output schema with test counts, coverage, per-file coverage details, and failure details.
