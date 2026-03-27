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
   - **Default verdict is FIX. Do not rationalize away required work.**
   - "Pre-existing", "it was already like this", or "cosmetic" are NOT valid reasons for DEFER or ACCEPT
   - DEFER requires a concrete, structural reason: fix requires touching unrelated systems, carries real regression risk, or needs a separate migration
   - A one-line fix is never "out of scope"
   - **Human-in-the-loop rule**: if you want to DEFER or ACCEPT a CRITICAL or REQUIRED finding but lack a sufficient structural reason (i.e., your justification doesn't clearly fit "touches unrelated systems / regression risk / needs separate migration") — you MUST call ask_user. Present the finding, your proposed verdict, and your rationale. Let the user decide. Legitimate structural reasons don't need confirmation; soft justifications do.
   - DEFER rationale must be detailed enough to be actionable months later: what exactly is wrong, why it matters, why it can't be fixed now, and what a fix would involve
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
