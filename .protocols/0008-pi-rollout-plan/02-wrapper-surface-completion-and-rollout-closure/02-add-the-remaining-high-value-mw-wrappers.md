---
id: 02-wrapper-surface-completion-and-rollout-closure-02-add-the-remaining-high-value-mw-wrappers
status: pending
estimate: 3h
---
# Add the remaining high-value `/mw` wrappers

## Objective

<!-- objective -->
Complete the wrapper surface for the most important existing project workflows so users can rely on pi-native commands instead of remembering raw workflow names. This closes the remaining wrapper portion of the rollout without changing the underlying shared workflows.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Implement the remaining wrappers against existing workflows

Each wrapper should be a thin adapter over the workflow that already exists in the project.

- [ ] Add `/mw merge-protocol [arg]` using shared protocol resolution
  Resolve the protocol directory the same way the protocol wrappers already do, then start the existing `merge-protocol` workflow.

- [ ] Add `/mw commit`, `/mw code-review`, `/mw testing`, and `/mw verify-fix`
  Map each command to the existing workflow entrypoint with only the minimum pre-start validation or inferred context needed.

- [ ] Normalize wrapper help, usage, and error messages
  Present a coherent command family so users can discover wrapper behavior without diving into source code.

<!-- accept -->
- Each new `/mw` command starts the corresponding existing workflow rather than reimplementing it in the extension.
- Protocol-based wrappers reuse shared protocol resolution helpers instead of introducing bespoke lookup code.
- Wrapper usage and error messaging is consistent across the `/mw` command family.
<!-- /accept -->
<!-- /task -->

<!-- task -->
### Cover the wrapper family with integration tests

Command-surface growth should be protected by the existing regression harness.

- [ ] Add focused tests for each new wrapper path
  Verify command parsing, workflow name selection, and variable mapping at the extension boundary.

- [ ] Keep the broader integration suite green
  Use the full suite as a guardrail against regressions between generic workflow commands, native skill work, and wrapper expansions.

<!-- accept -->
- New wrapper commands have integration tests proving they invoke the intended workflows and variables.
- The full `memento-pi` integration suite remains green after the wrapper expansion.
- No wrapper relies on a manual backend start or manual relay workaround.
<!-- /accept -->
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- Keep wrappers thin and workflow-backed.
- Do not add brand-new workflow semantics under the `/mw` namespace as part of rollout completion.
- Prefer explicit follow-up backlog items over silently widening this step's scope.
<!-- /constraints -->

## Implementation Notes

If one of these wrappers reveals a missing backend/workflow contract, fix that contract rather than embedding more logic in the wrapper layer.

## Verification

<!-- verification -->
```bash
cd memento-pi && npm run typecheck
cd memento-pi && npm run test:integration
```
<!-- /verification -->

## Context

<!-- context:inline -->
The original wrapper backlog remains relevant, but the protocol should now treat it as a focused remaining-surface task rather than the main story of the rollout.
<!-- /context:inline -->

<!-- context:files -->
- memento-pi/memory/pi-rollout-plan.md
- memento-pi/memory/pi-rollout-checklist.md
- .workflows/
<!-- /context:files -->

## Starting Points

<!-- starting_points -->
- memento-pi/src/index.ts
- memento-pi/tests/
- .workflows/
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] memento-pi/memory/pi-rollout-checklist.md
- [ ] memento-pi/README.md
