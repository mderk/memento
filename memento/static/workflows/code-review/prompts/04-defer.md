# Defer Findings to Backlog

Create backlog items for deferred findings from the code review.

## Findings

{{results.synthesize}}

## Instructions

Look at the findings above. For each finding with `verdict: "DEFER"`, call `/defer` with:

- **title**: the finding description (truncated to ~80 chars)
- **type**: `debt`
- **priority**: map severity — CRITICAL→p0, REQUIRED→p1, SUGGESTION→p2
- **area**: the competency field (first one if comma-separated)
- **origin**: `code-review`
- **description**: `{file}:{line} — {description}`

If there are no DEFER findings, skip and report "No deferred findings."

Do NOT create items for findings with verdict FIX, ACCEPT, or null.
