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
   - **REQUIRED/CRITICAL findings must be FIX** unless `pre_existing` is true (then DEFER is allowed)
   - If you disagree that a new REQUIRED finding needs FIX, do NOT silently DEFER or downgrade it. Instead, call ask_user: present the finding and your rationale, let the user decide between FIX and DEFER
   - Build a triage table referencing findings by index and include it in `triage_table`:
     ```
     | # | Finding | Verdict | Rationale |
     |---|---------|---------|-----------|
     | 0 | shell=True in scanner | DEFER | Pre-existing, not in current diff |
     | 1 | Missing input validation | FIX | Introduced in this diff |
     ```
5. Set `has_blockers` to true only if any finding has verdict **FIX** (a DEFER'd pre-existing issue is not a blocker)
6. Determine overall verdict:
   - **APPROVE**: No findings with verdict FIX
   - **APPROVE_WITH_COMMENTS**: Only SUGGESTION findings or all CRITICAL/REQUIRED are DEFER/ACCEPT
   - **REQUEST_CHANGES**: Has findings with verdict FIX

## Output

Respond with a JSON object matching the output schema with the combined findings, has_blockers flag, and verdict.
