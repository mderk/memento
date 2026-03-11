# Verify Red (Tests Should Fail)

Run the newly written tests and verify they FAIL as expected (since production code hasn't been written yet).

## Instructions

1. Identify the test files that were just created or modified
2. Run ONLY those specific test files using the project's test runner
3. Verify the tests FAIL (not due to import errors, but due to missing/incorrect behavior)
4. Report the status:
   - **red**: Tests fail as expected (correct — proceed to implementation)
   - **green**: Tests pass unexpectedly (investigate — tests may be wrong or behavior already exists)
   - **error**: Tests can't run (fix imports/structure)

## Output

Respond with a JSON object matching the output schema with the test status and any failure/error details.
