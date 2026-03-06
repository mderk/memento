# Fix Failures

Fix the lint or test failures reported in the previous verification step.

## Failures

{{results.verify-green}}

## Instructions

1. Read the failure details from the verification results
2. Analyze each failure:
   - Lint errors: fix code style issues
   - Type errors: fix type annotations or logic
   - Test failures: fix PRODUCTION code (not tests — tests are the spec)
3. Apply fixes to the affected files
4. Do NOT modify test files unless the test has a genuine bug (not a spec issue)

## Constraints

- Fix production code, not test code
- Tests define expected behavior — make code match tests
- Fix all reported issues before completing
