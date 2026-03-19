# Acceptance Check

Audit the current diff against the task requirements. Determine whether every requirement has both implementation and test coverage.

## Working Directory

All file reads must target `{{variables.workdir}}`.

## Unit

{{variables.unit}}

## Instructions

1. Extract a list of discrete requirements from the unit description above. Only include requirements that are explicitly stated — do not inflate from subtasks or implied work.
2. Run `git diff HEAD` in the workdir to see all changes made.
3. For each requirement, check:
   - **Implementation**: is there production code that fulfills it?
   - **Test coverage**: is there at least one test that would fail if the requirement broke?
4. If a requirement initially extracted turns out to be ambiguous or tangential to the actual task (e.g., implied by the description but not really asked for), move it to `out_of_scope` instead of `missing`.

## Output

Return `AcceptanceOutput` JSON. Set `passed` to true only if `missing` is empty.

## Constraints

- Do NOT fix anything. This is a read-only audit.
- Do NOT modify any files.
- Be pragmatic: a requirement is "covered" if there is reasonable implementation and test coverage, not perfect coverage.
- Implicit requirements (error handling, edge cases) that weren't part of the task description should not be flagged as missing.
