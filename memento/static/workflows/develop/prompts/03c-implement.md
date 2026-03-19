# Implement Code (GREEN phase)

Write the minimal production code to make the failing tests pass.

## Task

{{variables.task_compact}}

## Unit

{{variables.unit}}

## Failing Tests

{{variables.verify_red}}

## Instructions

1. Read the failing test files to understand exactly what behavior is expected
2. Read existing production code to understand patterns and conventions
3. Write the MINIMAL code needed to make the tests pass:
   - Follow existing code patterns (naming, structure, error handling)
   - Don't over-engineer or add features beyond what tests require
   - Don't add error handling unless tests require it
4. If you spot obvious mechanical errors in test files (import errors, typos, wrong fixture names, syntax errors), fix them. Do NOT change assertion logic or expected values — those define the spec.
5. Lint and test verification runs automatically after this step — focus on making tests pass

## Bash usage

- **Allowed**: installing dependencies, running generators, creating directories
- **Add backend dep**: `{{variables.commands.add_dep_backend}} <package>`
- **Add frontend dep**: `{{variables.commands.add_dep_frontend}} <package>`
- **Forbidden**: running tests, linting, type-checking, or any verification — the workflow runs these automatically in the next step

## Constraints

- Focus on production code; only fix mechanical test errors (imports, typos, fixtures)
- Do not change test assertions or expected values
- Follow existing project patterns
- Minimal implementation — just enough to pass tests
