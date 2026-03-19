# Acceptance Check

Audit the current diff against the unit requirements.

## Working Directory

All file reads must target `{{variables.workdir}}`.

## Unit

{{variables.unit}}

## Instructions

1. Read the unit description above. Extract **3-7 high-level requirements** — group related subtasks into single requirements. A requirement is a capability, not a checkbox item. For example, "upload with streaming and MIME validation" is one requirement, not three.
2. Run `git diff HEAD` in the workdir to see all changes made.
3. For each requirement, check if there is production code AND at least one test. Record a short evidence string (e.g. "MediaService.upload() + test_upload_valid_mime").
4. If a requirement is ambiguous or tangential, move it to `out_of_scope`.

## Output

Return `AcceptanceOutput` JSON. Set `passed` to true only if `missing` is empty.

## Constraints

- Do NOT fix anything. This is a read-only audit.
- Do NOT modify any files.
- Requirements should be high-level capabilities (3-7 total), not individual subtasks.
- Evidence strings in `covered` should be short (function/test names), not full descriptions.
