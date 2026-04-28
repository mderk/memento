---
id: 02-wrapper-surface-completion-and-rollout-closure-01-add-mw-develop-and-reusable-wrapper-scaffolding
status: pending
estimate: 1h30m
---
# Add `/mw develop` and reusable wrapper scaffolding

## Objective

<!-- objective -->
Finish the first missing non-protocol wrapper and establish the minimal structure needed to add the rest without turning `src/index.ts` into an unmaintainable command blob. This step proves that wrapper work can continue cleanly beyond the already-landed protocol commands.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Extract shared wrapper helpers where they now pay off

The code already has protocol-specific helpers; extending wrappers further should not duplicate start plumbing or argument validation everywhere.

- [ ] Move or factor shared wrapper logic into reusable helpers/modules
  Keep command dispatch readable while reusing common pieces such as backend start calls, validation helpers, and protocol resolution where applicable.

- [ ] Preserve the `/wf` vs `/mw` split in the implementation structure
  Wrapper convenience logic should stay clearly separate from generic workflow control code.

<!-- accept -->
- Adding new `/mw` wrappers does not require copying large blocks of near-identical command-start logic.
- The generic `/wf` command implementation remains distinct from project-wrapper concerns.
- Shared wrapper helpers are reusable from at least one non-protocol wrapper.
<!-- /accept -->
<!-- /task -->

<!-- task -->
### Implement `/mw develop` end to end

This is the smallest remaining wrapper and the right proving ground for the shared wrapper structure.

- [ ] Validate non-empty task input
  Reject empty or whitespace-only task strings before contacting the backend.

- [ ] Start the existing `development` workflow with the expected variables
  Keep the wrapper thin: map arguments to `{ task }`, call the real workflow, and reuse the existing runtime/relay path.

- [ ] Add integration coverage for `/mw develop`
  Prove the wrapper launches the intended workflow with the expected variables on a real test harness path.

<!-- accept -->
- `/mw develop <task>` starts the real `development` workflow with the provided task string.
- Blank task input is rejected with a clear usage error.
- Integration tests cover the `/mw develop` wrapper path.
<!-- /accept -->
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- Do not reimplement workflow logic in wrappers.
- Keep wrapper work thin and centered on pre-start argument handling.
- Avoid large unrelated refactors while extracting reusable command helpers.
<!-- /constraints -->

## Implementation Notes

This step is intentionally modest: get one clean non-protocol wrapper in place, and only extract as much structure as is needed to make the next wrapper additions straightforward.

## Verification

<!-- verification -->
```bash
cd memento-pi && npm run typecheck
cd memento-pi && npm run test:integration
```
<!-- /verification -->

## Context

<!-- context:inline -->
The protocol wrappers already landed, so `/mw develop` is now the smallest remaining wrapper that still proves the general wrapper pattern.
<!-- /context:inline -->

<!-- context:files -->
- memento-pi/memory/pi-rollout-plan.md
- memento-pi/memory/pi-rollout-checklist.md
<!-- /context:files -->

## Starting Points

<!-- starting_points -->
- memento-pi/src/index.ts
- memento-pi/src/commands/protocols.ts
- memento-pi/tests/
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] memento-pi/memory/pi-rollout-checklist.md
- [ ] memento-pi/README.md
