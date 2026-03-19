# Testing Review

## Scope

Test correctness and usefulness, coverage gaps, determinism/flakiness, isolation, speed, and maintainability.

## Principles

- Code is incomplete without tests (unless explicitly justified).
- Test pyramid: many fast unit tests, some integration, few E2E.
- Flaky tests destroy CI value and must be treated as regressions.

## Rules

### 1. Tests prove behavior (not implementation)

- Executable specifications: setup → action → assertion(s)
- Assert observable outcomes, not internal call order/private methods
- At least one assertion fails if change is reverted
- Bug fixes include regression tests

### 2. Coverage matches risk

- **Changed files must have 100% line coverage** — if a file was touched in this PR, every line must be covered. Untested legacy code in the same file must also be covered: touching a file means owning its coverage.
- New/changed behavior is covered (happy + edge/error)
- High-risk paths get stronger coverage: auth/permissions/ownership, data migrations/integrity constraints, payments/billing, background tasks/idempotency

### 3. Determinism and anti-flakiness

- No bare sleeps; use framework waits/polling/callbacks
- Time controlled (inject/freeze, explicit timezones)
- Randomness controlled (fixed seed / deterministic fixtures)
- Order-independent, parallel-safe
- No external network/services; mock at boundaries

### 4. Isolation and cleanup

- Each test owns setup+cleanup; cleanup on failure too
- No global mutable state leaks (singletons, caches, env vars, mocked modules)
- DB state isolated (transactions/rollbacks or fresh fixtures)

### 5. Signal quality (assertions)

- No weak assertions ("status 200" without checking response body)
- Assert user/system contract (API schema, permissions, invariants)
- Mock external boundaries, not internal helpers

### 6. Speed and maintainability

- Unit tests: fast, hermetic (no real network/disk/DB)
- Clear Arrange/Act/Assert structure
- Avoid huge snapshots unless stable and high-signal

## Anti-Patterns

| Anti-Pattern | Why it's bad | Fix |
|---|---|---|
| Bare sleeps for async | Flaky and slow | Framework waits/polling/callbacks |
| Tests depend on order/shared state | Non-deterministic failures | Isolate state; reset globals/fixtures |
| Real external calls (LLM/S3/HTTP) | Flaky, slow, costly | Mock/stub at boundaries |
| Weak assertions | False confidence | Assert contract-critical outputs |
| Over-mocking internals | Tests break on refactor | Mock boundaries, test behavior |

## Severity

- **[CRITICAL]**: Flaky/nondeterministic tests; tests hitting real external services; tests that pass while critical behavior is broken; removing coverage for auth/permissions/data integrity without replacement; changed file below 100% line coverage.
- **[REQUIRED]**: Missing tests for behavior changes; no regression test for bug fix; bare sleeps; order-dependent tests; asserting implementation details; missing edge cases for risky changes.
- **[SUGGESTION]**: Readability/structure improvements; reduce duplication with parametrization/fixtures; strengthen assertions; narrow test scope where possible.
