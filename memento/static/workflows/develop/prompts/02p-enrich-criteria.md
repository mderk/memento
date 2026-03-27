# Enrich Acceptance Criteria

Generate acceptance criteria for protocol units that don't have them.

## Units

{{variables.units}}

## Instructions

For each unit in the list above:

1. If `acceptance_criteria` is **non-empty** — pass the unit through unchanged (keep all fields as-is).
2. If `acceptance_criteria` is **empty** — generate 2-5 concrete, verifiable acceptance criteria from the unit's `description`.

### Criteria quality rules

- Focus on **observable behavior**, not implementation details
- Each criterion should be independently verifiable (can check without seeing other criteria)
- Use concrete language: "endpoint returns 200 with JWT token", not "authentication works"
- Avoid tautologies: don't restate the task heading as a criterion

## Output

Return an `EnrichCriteriaOutput` JSON object with all units, preserving their `id`, `description`, and `depends_on` fields exactly. Only `acceptance_criteria` may be added or left unchanged.
