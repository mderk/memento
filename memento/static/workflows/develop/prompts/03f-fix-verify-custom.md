# Fix Custom Verification Failures

Fix failures from protocol-specific verification commands.

## Verification Results

{{variables.verify_custom}}

## Working Directory

All file reads and edits must target `{{variables.workdir}}`.

## Instructions

1. Focus only on commands where `passed` is `false`.
2. Fix the underlying issue in code/config/scripts so the failing command(s) pass.
3. Do not weaken or delete verification commands. Treat them as acceptance criteria.
4. Keep changes minimal and localized.
5. You do not need to run verification commands manually — the workflow will re-run:
   - `verify-custom` (these commands)
   - `verify-fix` (lint + tests)

## Constraints

- Prefer fixing production code/config. Avoid changing tests unless the failure is clearly a mechanical test error.
- Do not edit protocol step files; only change files inside the working directory.
