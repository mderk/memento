---
id: 03-p1-wrapper-expansion-and-release-hardening-02-add-the-remaining-mw-workflow-wrappers
status: pending
estimate: 3h
---
# Add the remaining `/mw` workflow wrappers

## Objective

<!-- objective -->
Complete the pi-native wrapper surface for the existing shared workflows so common project entrypoints can be invoked directly from pi. Each wrapper should remain a thin adapter over an existing workflow rather than a new control plane.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Implement protocol-aware and generic project wrappers

Finish the planned command surface using the shared wrapper scaffolding from the prior step.

- [ ] Add `/mw merge-protocol [arg]` using protocol resolution helpers
  Resolve the target protocol directory and start the existing `merge-protocol` workflow without custom merge logic in pi.

- [ ] Add `/mw commit`, `/mw code-review`, `/mw testing`, and `/mw verify-fix`
  Map command arguments and inferred context into the variables expected by the existing workflows. Keep behavior narrowly focused on pre-start setup.

- [ ] Normalize user-facing help and error messages across wrappers
  Ensure commands explain required input clearly and fail consistently when prerequisites are missing.

<!-- accept -->
- Each planned `/mw` wrapper starts the corresponding existing workflow instead of reimplementing it in the extension.
- Protocol-based wrappers reuse the shared protocol resolution path rather than custom per-command lookup code.
- Wrapper errors and usage prompts are consistent enough that a user can discover the command family without reading source code.
<!-- /accept -->
<!-- /task -->

<!-- task -->
### Expand integration coverage for the wrapper family

The wrapper surface should remain safe to evolve after rollout.

- [ ] Add focused integration tests for each new wrapper path
  Verify command parsing, workflow selection, and variable mapping at the extension boundary.

- [ ] Keep the existing integration suite green as a regression gate
  Use the broader suite to catch interactions between generic commands, wrapper commands, and backend bootstrap changes.

<!-- accept -->
- New wrapper commands have integration coverage that proves they invoke the intended workflow names and variables.
- The full `memento-pi` integration suite remains green after the wrapper expansion.
- No wrapper requires a manual backend start or a custom relay bypass.
<!-- /accept -->
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- Do not widen wrapper scope beyond pre-start logic and argument normalization.
- Reuse shared command helpers instead of duplicating protocol resolution or start plumbing.
- Keep compatibility with the unchanged shared workflow definitions.
<!-- /constraints -->

## Implementation Notes

Treat this as command-surface completion, not a place to add new workflow semantics. If a wrapper needs behavior the underlying workflow cannot support, fix the workflow or backend contract rather than embedding logic in pi.

## Verification

<!-- verification -->
```bash
cd memento-pi && npm run typecheck
cd memento-pi && npm run test:integration
```
<!-- /verification -->

## Context

<!-- context:inline -->
This step covers the remaining P1 wrapper backlog from the rollout plan: `merge-protocol`, `commit`, `code-review`, `testing`, and `verify-fix`. The shared workflows remain the implementation authority.
<!-- /context:inline -->

<!-- context:files -->
- memento-pi/memory/pi-rollout-plan.md
- memento-pi/memory/pi-rollout-checklist.md
- memento-pi/memory/overview.md
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
