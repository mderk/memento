---
id: 02-wrapper-surface-completion-and-rollout-closure-03-run-final-rollout-acceptance-and-close-the-protocol
status: pending
estimate: 2h
---
# Run final rollout acceptance and close the protocol

## Objective

<!-- objective -->
End the rollout with a truthful acceptance pass over the integrated path and aligned documentation. This step should make it obvious which goals are complete, which commands are supported, and whether any non-goals must be deferred explicitly.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Verify the key end-to-end acceptance paths

The rollout should be judged on the real integrated experience, not only on isolated code changes.

- [ ] Run backend and extension regression suites together
  Use the existing Python and TypeScript verification commands as the release gate for the integrated rollout.

- [ ] Spot-check the critical user flows
  Confirm `/skill:create-protocol` or equivalent native skill path, `/wf list`, `/wf resume`, `/mw create-protocol`, `/mw process-protocol`, and `/mw develop` all work through the intended backend runtime path.

- [ ] Defer any remaining non-goals explicitly
  If relay simplification, optional `memento` environment wrappers, or other follow-up work remains, capture it deliberately rather than leaving implicit gaps.

<!-- accept -->
- The key rollout paths are verifiable through the real chain: command or skill -> extension runtime -> backend workflow.
- Backend and extension regression suites pass at the same time for the final acceptance pass.
- Remaining out-of-scope items are explicitly deferred instead of being silently left unfinished.
<!-- /accept -->
<!-- /task -->

<!-- task -->
### Align final docs and protocol state

Close the loop between what shipped, what the docs say, and what the protocol directory reports.

- [ ] Update protocol progress and related memory notes
  Mark completed work accurately and ensure the protocol directory tells the truth about remaining versus finished rollout work.

- [ ] Leave the command surface and config story discoverable for future sessions
  Make sure a new contributor can determine how `memento-pi` is configured, how workflows are started, and which entrypoints are officially supported.

<!-- accept -->
- Protocol progress reflects actual completion state at the end of the rollout.
- Memory notes and README are aligned on supported command paths and configuration.
- A future session can pick up the rollout state without re-deriving the architecture from code.
<!-- /accept -->
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- Do not hide unresolved issues behind vague 'mostly done' language.
- Use the real integrated path for acceptance instead of mocked shortcuts.
- Keep final closure focused on truthfulness, validation, and explicit follow-up capture.
<!-- /constraints -->

## Implementation Notes

This step is where the rollout stops being an implementation effort and becomes a supportable product path. It should leave the repo easier to reason about than it was before the rollout began.

## Verification

<!-- verification -->
```bash
cd memento-workflow && uv run pytest
cd memento-workflow && uv run pyright
cd memento-pi && npm run typecheck
cd memento-pi && npm run test:integration
```
<!-- /verification -->

## Context

<!-- context:inline -->
The original rollout acceptance criteria were split across P0a, P0, and P1. This final step consolidates them around the updated native-skill-first reality and whatever wrapper/release work remains.
<!-- /context:inline -->

<!-- context:files -->
- memento-pi/memory/pi-rollout-plan.md
- memento-pi/memory/pi-rollout-checklist.md
- memento-pi/README.md
- memento-pi/memory/README.md
<!-- /context:files -->

## Starting Points

<!-- starting_points -->
- memento-pi/README.md
- memento-pi/memory/pi-rollout-checklist.md
- memento-pi/tests/
- memento-workflow/tests/
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] memento-pi/memory/pi-rollout-checklist.md
- [ ] memento-pi/memory/README.md
- [ ] memento-pi/README.md
