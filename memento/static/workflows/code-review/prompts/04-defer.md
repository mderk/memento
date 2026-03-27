# Defer Findings to Backlog

Create backlog items for deferred findings from the code review.

## Findings

{{results.synthesize}}

## Instructions

Look at the findings above. For each finding with `verdict: "DEFER"`, call `/defer` with:

- **title**: concise but specific (~80 chars) — must be understandable without reading the code
- **type**: `debt`
- **priority**: map severity — CRITICAL→p0, REQUIRED→p1, SUGGESTION→p2
- **area**: the competency field (first one if comma-separated)
- **origin**: `code-review`
- **description**: a **self-contained** paragraph that answers all four questions:
  1. **What's wrong**: the specific problem (not just a label — explain it)
  2. **Why it matters**: impact if left unfixed (bug risk, maintenance cost, security exposure)
  3. **Why deferred**: the structural reason it can't be fixed in this PR
  4. **How to fix**: concrete approach or pointers for whoever picks this up

**Anti-pattern** — never write descriptions like these:
- `"protocol_md.py:427 — ItemWrapper mixed abstraction"` — meaningless without context
- `"test_protocol_helpers.py:703 — import pytest inside method body [pre-existing]"` — no explanation of why it matters

A backlog item that requires reading the code to understand the problem is a useless backlog item.

If there are no DEFER findings, skip and report "No deferred findings."

Do NOT create items for findings with verdict FIX, ACCEPT, or null.
