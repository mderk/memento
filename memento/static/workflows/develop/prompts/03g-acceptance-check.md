# Acceptance Check

Verify the implementation against acceptance criteria.

## Working Directory

All file reads must target `{{variables.workdir}}`.

## Units

{{variables.units}}

## Instructions

1. Collect all `acceptance_criteria` from every unit above into a flat list. Each unit's `acceptance_criteria` is a list of strings — concrete, verifiable statements about what the implementation must do.

2. **Fallback**: If ALL units have empty `acceptance_criteria`, fall back to extracting 3-7 high-level requirements from the unit descriptions. Group related subtasks into single requirements.

3. Run `git diff HEAD` in the workdir to see all changes made.

4. For each criterion (or extracted requirement), check if there is:
   - Production code implementing it
   - At least one test covering it
   Record a short evidence string (e.g. "MediaService.upload() + test_upload_valid_mime") in `covered`.

5. If no evidence exists for a criterion → add to `missing`.

6. Set `passed` to true only if `missing` is empty.

## Output

Return `AcceptanceOutput` JSON with `covered`, `missing`, and `passed` fields.

## Constraints

- Do NOT fix anything. This is a read-only audit.
- Do NOT modify any files.
- Evidence strings in `covered` should be short (function/test names), not full descriptions.
