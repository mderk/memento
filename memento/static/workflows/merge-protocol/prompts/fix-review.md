# Fix Code Review Findings

Address the code review findings that were triaged as FIX.

## Review Results

{{results.review}}

## Working Directory

All file reads and edits must target `{{variables.workdir}}`.
Paths in review findings are relative to the working directory.

## Instructions

1. Read the review findings from the results
2. For each finding with verdict FIX:
   - Read the affected file in `{{variables.workdir}}/`
   - Understand the issue and suggested fix
   - Apply the fix following existing code patterns
3. For CRITICAL findings: fix immediately
4. For REQUIRED findings: fix before proceeding
5. Do NOT fix DEFER or ACCEPT findings

## Constraints

- Only fix findings triaged as FIX
- Follow existing code patterns
- Do not modify test assertions (fix production code)
- All file operations must target the working directory
