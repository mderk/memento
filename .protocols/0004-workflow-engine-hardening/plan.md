---
status: In Progress
---
# Protocol: Workflow Engine Hardening

**Status**: Draft
**Created**: 2026-03-21
**PRD**: [./prd.md](./prd.md)

## Context

Protocol 0003 execution revealed develop workflow bugs (coverage retry wastes ~90s on stagnant numbers, acceptance check audits only the last unit) and engine debt (child run eviction safety, sandbox audit trail, blanket parallel downgrade in child runs).

## Decision

Fix in 3 steps ordered by blast radius: workflow definition fixes (safest), engine hardening (small targeted fixes), then parallel downgrade removal (structural but well-understood change).

## Rationale

Workflow fixes (step 1) are pure definition changes with zero engine risk. Engine hardening (step 2) is two isolated fixes in runner.py and sandbox.py. Parallel downgrade removal (step 3) is a single guard removal — analysis showed the infrastructure (composite run_ids, recursive checkpoint loading) already supports grandchild runs.

## Consequences

### Positive

- Coverage retry exits immediately on stagnation — saves ~60s per protocol step
- All units audited by acceptance check — no silent skips
- Child run eviction is safe against parent references
- Sandbox-off is logged for security audit
- Parallel blocks inside SubWorkflow run concurrently — code reviews ~4x faster

### Negative

- Removing parallel downgrade may surface edge cases in deeply nested workflows — mitigated by comprehensive existing test suite and recursive checkpoint infrastructure

## Progress

- [ ] [Fix workflows: coverage stagnation, acceptance scope, plan.json edit](./01-fix-develop-workflow-coverage-stagnation-and-acceptance-scop.md) <!-- id:01-fix-develop-workflow-coverage-stagnation-and-acceptance-scop --> — 2h est

- [ ] [Harden engine: eviction safety and sandbox audit](./02-harden-engine-eviction-safety-and-sandbox-audit.md) <!-- id:02-harden-engine-eviction-safety-and-sandbox-audit --> — 1h est

- [ ] [Remove parallel downgrade in child runs](./03-remove-parallel-downgrade-in-child-runs.md) <!-- id:03-remove-parallel-downgrade-in-child-runs --> — 2h est
