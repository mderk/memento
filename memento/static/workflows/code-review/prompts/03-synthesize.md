# Synthesize Review Findings

Combine all competency review results into a single report with overall recommendation.

## Individual Reviews

{{results}}

## Instructions

1. Collect all findings from the parallel competency reviews
2. Deduplicate findings (same issue flagged by multiple competencies)
3. Sort by severity: CRITICAL first, then REQUIRED, then SUGGESTION
4. Triage every CRITICAL and REQUIRED finding individually — no batch dismissal:
   - Assign a verdict to each: **FIX** (must resolve now), **DEFER** (track for later), or **ACCEPT** (acceptable as-is) with rationale
   - **Default is FIX.** To choose DEFER, you must provide a concrete reason (out of scope, requires separate migration, high risk to change now). "It was already like this" is NOT a valid reason — evaluate the problem itself, not when it appeared
   - If you are unsure whether a REQUIRED finding warrants FIX or DEFER, do NOT silently DEFER. Instead, call ask_user: present the finding and your rationale, let the user decide
   - Build a triage table referencing findings by index and include it in `triage_table`:
     ```
     | # | Finding | Verdict | Rationale |
     |---|---------|---------|-----------|
     | 0 | shell=True in scanner | DEFER | Fixing requires refactoring subprocess calls across 4 modules — out of scope |
     | 1 | Missing input validation | FIX | User input reaches SQL query unsanitized |
     ```
5. Set `has_blockers` to true only if any finding has verdict **FIX**
6. Determine overall verdict:
   - **APPROVE**: No findings with verdict FIX
   - **APPROVE_WITH_COMMENTS**: Only SUGGESTION findings or all CRITICAL/REQUIRED are DEFER/ACCEPT
   - **REQUEST_CHANGES**: Has findings with verdict FIX

## Output

Respond with a JSON object matching the output schema with the combined findings, has_blockers flag, and verdict.
