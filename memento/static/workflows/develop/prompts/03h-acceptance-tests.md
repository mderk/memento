# Write Acceptance Tests (RED phase)

Write tests for requirements that the acceptance check identified as missing coverage.

## Missing Requirements

{{results.acceptance-check.structured_output}}

## Working Directory

All file edits must target `{{variables.workdir}}`.

## Instructions

1. For each requirement listed in `missing`, write a test that validates the requirement.
2. Phrase tests as "would fail if the requirement broke" — not "must fail right now".
   Some gaps are test-only (implementation exists but tests don't), so the new tests may already pass.
3. Follow the project's existing test conventions (framework, patterns, file organization).
4. Place tests in the appropriate test files alongside existing tests.

## Output

Return `AcceptanceTestsOutput` JSON with `test_files` listing all test files you created or modified (paths relative to the workdir root).

## Constraints

- Write ONLY test files. Do NOT write any production code.
- Do NOT modify existing test assertions.
- Do NOT run tests — the workflow runs them automatically in the next step.
