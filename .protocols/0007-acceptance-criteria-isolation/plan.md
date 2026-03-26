---
status: In Progress
---
# Protocol: Acceptance Criteria + Evaluator Isolation

**Status**: Draft
**Created**: 2026-03-25
**PRD**: [./prd.md](./prd.md)

## Context

The develop workflow's acceptance check suffers from self-evaluation bias: it runs in the same context as implementation, extracts its own requirements on the fly, and has escape hatches (`out_of_scope`) that let the model rationalize gaps. Write-tests sees explore/plan context, biasing tests toward implementation rather than behavior.

## Decision

Define acceptance criteria **before coding** at the unit level. Isolate evaluator (acceptance check) and test writer (write-tests) as subagents so they operate from spec only, without implementation context. Remove unused `files`/`test_files` from PlanTask; wire verify-red to write-tests output instead.

Three coordinated changes:
1. **Schema + data flow**: new fields, simplified output, write-tests returns created files
2. **Prompt rewrites**: plan generates criteria, acceptance check verifies against them, write-tests returns file list
3. **Workflow wiring**: subagent isolation, verify-red reads from write-tests result, parser handles `<!-- accept -->` blocks

## Rationale

**Why not keep acceptance check in main context?** Self-evaluation bias — the model that wrote code can't objectively assess it. Anthropic's harness design article confirms: isolating the evaluator is more tractable than making generators self-critical.

**Why not keep write-tests in main context?** Anti-TDD — seeing explore/plan details biases tests toward specific implementation rather than behavior.

**Why remove files/test_files from PlanTask?** They're not used by write-tests or implement prompts. `test_files` is used by verify-red but often doesn't match what write-tests actually creates — a latent bug.

## Consequences

### Positive

- Acceptance check can't rationalize gaps — criteria are fixed inputs, not self-generated
- Write-tests produces behavior-driven tests, not implementation-coupled
- Acceptance criteria steer generation — implement sees them in unit JSON
- Verify-red runs actual created test files, not predicted ones
- Simpler PlanTask schema — planner focuses on what matters (description + criteria)

### Negative

- Write-tests as subagent loses context from explore/plan — must discover project conventions by reading codebase (already does this per prompt instructions)
- Acceptance check as subagent adds one agent call — cost acceptable for the isolation benefit
- Old step files without <!-- accept --> blocks need fallback — acceptance check must detect and extract from description

## Progress

- [x] [Update schemas and unit data flow](./01-update-schemas-and-unit-data-flow.md) <!-- id:01-update-schemas-and-unit-data-flow --> — 2h est

- [ ] [Rewrite prompts for criteria-driven flow](./02-rewrite-prompts-for-criteria-driven-flow.md) <!-- id:02-rewrite-prompts-for-criteria-driven-flow --> — 1h30m est

- [ ] [Wire subagent isolation and verify-red fix](./03-wire-subagent-isolation-and-verify-red-fix.md) <!-- id:03-wire-subagent-isolation-and-verify-red-fix --> — 1h30m est
