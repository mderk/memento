# Fix Code Review Findings

Address the code review findings that were triaged as FIX.

## Review Results

{{results.review}}

## Instructions

1. Read the review findings from the results
2. For each finding with verdict FIX:
   - Read the affected file
   - Understand the issue and suggested fix
   - Apply the fix following existing code patterns
   - Verify the fix doesn't break other functionality
3. For CRITICAL findings: fix immediately
4. For REQUIRED findings: fix before proceeding
5. Run lint/type checks after fixes
6. Do NOT fix DEFER or ACCEPT findings

## Constraints

- Only fix findings triaged as FIX
- Follow existing code patterns
- Run lint after changes
- Do not modify test assertions (fix production code)
