---
id: 03-p1-wrapper-expansion-and-release-hardening-01-add-shared-wrapper-scaffolding-and-mw-develop
status: pending
estimate: 1h30m
---
# Add shared wrapper scaffolding and `/mw develop`

## Objective

<!-- objective -->
Establish a maintainable home for pi workflow wrappers, then add the simplest project wrapper (`/mw develop`) as the template for the rest. This lowers the risk of command sprawl before the full wrapper set is added.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Extract reusable wrapper command structure

Avoid leaving all wrapper logic in a single monolithic entrypoint.

- [ ] Create command modules or helpers for wrapper registration
  Move shared concerns such as argument validation, workflow start invocation, and protocol helper reuse into a structure that can scale to multiple `/mw` commands.

- [ ] Keep `/wf` and `/mw` responsibilities distinct
  Use `/wf` only for generic workflow control and reserve `/mw` for project-oriented wrappers.

<!-- accept -->
- Wrapper registration is organized so adding new `/mw` commands does not require duplicating start logic in multiple places.
- The generic `/wf` namespace remains focused on workflow control rather than project-specific conveniences.
- Protocol helper code is reusable from wrapper modules rather than embedded in one-off command handlers.
<!-- /accept -->
<!-- /task -->

<!-- task -->
### Implement `/mw develop` end to end

Use the development workflow wrapper as the simplest proof that the wrapper pattern works beyond protocol commands.

- [ ] Validate non-empty task input
  Reject blank invocations before contacting the backend.

- [ ] Start the existing `development` workflow with `{ task }`
  Do only thin pre-start logic; relay behavior continues to come from the shared runtime.

- [ ] Add integration coverage for the wrapper
  Prove the wrapper path invokes the correct backend workflow with the expected variables.

<!-- accept -->
- `/mw develop <task>` starts the real `development` workflow with the provided task string.
- Blank or whitespace-only task input is rejected with a clear message.
- Integration coverage demonstrates that the wrapper path works on a real project without custom relay logic.
<!-- /accept -->
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- Do not fork the underlying development workflow.
- Keep wrapper logic thin and composable.
- Preserve the namespace split: `/wf` generic, `/mw` project wrappers.
<!-- /constraints -->

## Implementation Notes

This step should produce the command scaffolding that the rest of P1 reuses. If wrapper-specific options start to diverge, prefer typed helper functions over ad-hoc inline parsing in `index.ts`.

## Verification

<!-- verification -->
```bash
cd memento-pi && npm run typecheck
cd memento-pi && npm run test:integration
```
<!-- /verification -->

## Context

<!-- context:inline -->
The rollout plan explicitly recommends moving wrapper glue into `src/commands/*.ts` if command complexity grows. `/mw develop` is the best first consumer because it has the smallest pre-start contract.
<!-- /context:inline -->

<!-- context:files -->
- memento-pi/memory/pi-rollout-plan.md
- memento-pi/memory/pi-rollout-checklist.md
<!-- /context:files -->

## Starting Points

<!-- starting_points -->
- memento-pi/src/index.ts
- memento-pi/tests/protocol-wrappers.integration.test.ts
- memento-pi/package.json
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] memento-pi/memory/pi-rollout-checklist.md
- [ ] memento-pi/README.md
