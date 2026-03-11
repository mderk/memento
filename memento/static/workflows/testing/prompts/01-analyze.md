# Analyze Test Failures

Tests failed or coverage gaps were detected. Analyze and provide actionable feedback.

## Test Results

{{variables.test_result}}

## Instructions

1. Read each failing test file to understand expected behavior
2. Read relevant production code referenced in `failures` and `failure_excerpt`
3. For each failure, determine:
   - Root cause (what went wrong)
   - Suggested fix (specific code change needed)
   - Priority: CRITICAL (blocks merge), REQUIRED (must fix before ship), SUGGESTION (nice-to-have)
4. If `coverage_gaps` is true, review `gap_files` — identify what code paths are untested
5. Escalate to user when: flaky tests, unmockable external deps, cannot reach 100% coverage on changed files

## Output

Respond with a JSON object matching the output schema with test counts, coverage, per-file coverage details, and failure details.
