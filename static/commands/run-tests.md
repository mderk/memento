---
description: Run test-runner agent to execute tests
argument-hint: [test files or description]
---

You are tasked with running tests based on the user's request.

## Instructions

1. **Parse the test argument**: The user can provide specific test files, test patterns, free-form descriptions, or no arguments to run all tests.

2. **Launch the test-runner agent**: Use the Task tool with `subagent_type="test-runner"` to execute the tests.

3. **Provide context**: In your prompt to the test-runner agent, include:
   - The test description or file paths provided by the user
   - Any specific concerns or context from the user's request
   - Request the agent to find and execute the relevant tests, report results clearly, highlight failures, and suggest fixes

4. **Present results**: After the agent completes, summarize the test execution for the user with pass/fail counts and any critical failures.

## Example Usage

```
/run-tests server/tests/test_api.py
/run-tests test_authentication
/run-tests "test the user profile component"
/run-tests
```

## Important Notes

- The test-runner agent will auto-detect test framework if not specified
- If test description is ambiguous, the agent will search for matching test files
- Multiple test files can be executed in a single run
