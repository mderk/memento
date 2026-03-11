# Fix Code Review Findings

Address the code review findings that were triaged as FIX.

## Review Results

{{results.review}}

## Working Directory

If `{{variables.workdir}}` is set, all file reads and edits must target that directory.
Paths in review findings are relative to the working directory.

## Instructions

1. Read the review findings from the results
2. For each finding with verdict FIX:
   - Read the affected file (prepend `{{variables.workdir}}/` if workdir is set)
   - Understand the issue and suggested fix
   - Apply the fix following existing code patterns
   - Verify the fix doesn't break other functionality
3. For CRITICAL findings: fix immediately
4. For REQUIRED findings: fix before proceeding
5. Run lint/type checks after fixes (in the workdir if set)
6. Do NOT fix DEFER or ACCEPT findings

## Constraints

- Only fix findings triaged as FIX
- Follow existing code patterns
- Run lint after changes
- Do not modify test assertions (fix production code)
- All file operations must target the correct working directory
