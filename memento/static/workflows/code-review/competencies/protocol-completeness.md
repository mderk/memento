# Protocol / Spec Completeness Review

## Scope

Completeness, consistency, and implementability of protocol and specification documents. This competency extends the [Simplicity](./simplicity.md) rules to design documents that describe _planned_ code rather than existing code.

## When to Use

-   Reviewing `.protocols/*/` step files (API specs, flow descriptions, frontend pages, test plans)
-   Reviewing PRDs, technical specs, or implementation plans
-   **Trigger**: `/code-review` is invoked on protocol/spec files (`.md` files under `.protocols/`)

## Rules

### Implementability

-   Every code snippet can be implemented without additional questions
-   Function signatures match existing patterns in the codebase (verify by reading actual source files)
-   API contracts (request/response) are consistent between steps (e.g., endpoint name in step 01 matches what step 02 calls)
-   Auth patterns match existing codebase conventions (e.g., bot-auth vs user-auth endpoint namespaces)
-   Dependency injection, imports, and helpers referenced actually exist or are marked as "new"

### Consistency Between Steps

-   Endpoint paths, function names, and variable names are the same across all step files
-   Request/response formats in API step match what bot/frontend steps send/receive
-   Error handling described in API step matches what bot/frontend steps expect
-   Redis key formats, TTLs, and token formats are consistent across steps

### Edge Cases

-   What happens when the user abandons the flow mid-way?
-   What happens with concurrent requests?
-   What happens when external services (Redis, DB, third-party APIs) are unavailable?
-   What happens when the user is not authenticated or their session expires?
-   What happens on a different device or browser?
-   Are all failure paths covered with user-facing error messages?

### Verification

-   Verification commands are correct and actually work (`pytest -k` patterns match test names, paths exist)
-   Test plan covers all described edge cases
-   Test plan includes error paths, not just happy paths
-   Manual test steps are actionable and unambiguous
-   **No standard test/lint commands in the `<!-- verification -->` block.** This block is for protocol-specific commands that run in addition to the develop workflow's standard `verify-fix` phase. Putting the project's standard test/lint command there causes the suite to run twice. Flag as **[REQUIRED]** any verification block that:
    -   Re-runs the same test/lint/typecheck command the project already invokes via its standard `verify-fix` phase.
    -   Invokes a generic test runner without a narrow selector that targets only this step's new tests.
    -   If the step has nothing genuinely custom to verify, the block must be left **empty** — an empty block is correct, not a gap.
    -   A non-empty block is acceptable only when it runs a step-scoped subset the standard phase would not run, or a check the standard phase does not perform at all.

### YAGNI (inherited from Simplicity)

-   Protocol solves only the stated problem, no scope creep
-   No speculative abstractions or over-generalized solutions
-   Existing infrastructure reused where possible (no reinventing)

### Missing Pieces Checklist

-   [ ] Are translations mentioned for all new user-facing strings? (bot and frontend)
-   [ ] Is the frontend route protection described (AuthGuard, PublicRoute)?
-   [ ] Are Pydantic request/response schemas mentioned?
-   [ ] Is rate limiting mentioned for new endpoints?
-   [ ] Is logging/audit trail mentioned for security-sensitive operations?
-   [ ] Are existing helpers/utilities referenced correctly (do they exist)?
-   [ ] Is step ordering and parallelism noted?

## Anti-Patterns

| Anti-Pattern                | Signal                                                        | Why It Matters                        |
| --------------------------- | ------------------------------------------------------------- | ------------------------------------- |
| Pseudocode-reality mismatch | Snippet uses patterns that don't exist in codebase            | Implementer will get stuck or deviate |
| Auth boundary confusion     | User-auth endpoint under bot-auth namespace                   | Wrong auth applied, security gap      |
| Inconsistent naming         | Step 01 says `/create-token`, step 02 calls `/generate-token` | Integration bugs                      |
| Missing error handling      | Happy path only, no failure states                            | Incomplete implementation             |
| Untestable spec             | No verification commands or test plan                         | Quality regression                    |
| Duplicate verification      | `verification` block re-invokes the project's standard test/lint command | Test suite runs twice; hides the intent of the block (custom checks only) |

## Severity

-   **[CRITICAL]**: Spec contradicts itself between steps, or describes impossible/broken flow
-   **[REQUIRED]**: Missing information that would force implementer to guess, pattern mismatch with codebase, missing error handling
-   **[SUGGESTION]**: Minor clarifications, documentation improvements, edge case notes
