# Fix Failures

Fix the lint or test failures reported by the verification tools.

## Lint Results

{{variables.lint_result}}

## Test Results

{{variables.verify_green}}

## Working Directory

All file writes and edits must target `{{variables.workdir}}`.

## Instructions

1. Read the failure details from both lint and test results above
2. For lint errors: fix code style issues reported in `output`
3. For test failures: determine the root cause using this decision process:
   a. **Mechanical test error** — the test itself crashes before reaching an assertion (import error, syntax error, missing fixture, wrong variable name) → fix the test
   b. **Assertion failure** — the test runs but an assertion fails. Cross-reference the expected value with the task objective from earlier in the conversation:
      - Expected value matches the task objective → production code is wrong, fix it
      - Expected value contradicts the task objective → test is wrong, fix the assertion
   c. **Ambiguous** — re-read the task objective carefully. If still unclear, fix production code (safer default)
4. Apply fixes to the affected files

## Bash usage

- **Allowed**: installing dependencies, running generators, creating directories
- **Add backend dep**: `{{variables.commands.add_dep_backend}} <package>`
- **Add frontend dep**: `{{variables.commands.add_dep_frontend}} <package>`
- **Forbidden**: running tests, linting, type-checking, or any verification — the workflow re-runs these automatically after this step

## Constraints

- The source of truth is the **task objective**, not the tests or the current implementation — both were just written and may contain bugs
- Fix all reported issues before completing
