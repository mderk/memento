# Fix Failures

Fix the lint or test failures reported by the verification tools.

## Lint Results

{{variables.lint_result}}

## Test Results

{{variables.verify_green}}

## Instructions

1. Read the failure details from both lint and test results above
2. Analyze each failure:
   - Lint errors: fix code style issues reported in `output`
   - Type errors: fix type annotations or logic
   - Test failures: read the `failure_excerpt` and `failures` list, then fix PRODUCTION code (not tests — tests are the spec)
3. Apply fixes to the affected files
4. Do NOT modify test files unless the test has a genuine bug (not a spec issue)

## Constraints

- Fix production code, not test code
- Tests define expected behavior — make code match tests
- Fix all reported issues before completing
