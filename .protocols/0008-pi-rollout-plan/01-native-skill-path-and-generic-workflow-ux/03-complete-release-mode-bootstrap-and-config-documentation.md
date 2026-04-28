---
id: 01-native-skill-path-and-generic-workflow-ux-03-complete-release-mode-bootstrap-and-config-documentation
status: pending
estimate: 2h30m
---
# Complete release-mode bootstrap and config documentation

## Objective

<!-- objective -->
Turn the current development-friendly bootstrap into a documented release path. This step should make it clear how `memento-pi` starts the backend in normal use, how model alias/thinking config is supplied, and where local development fallbacks still apply.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Switch bootstrap defaults from local-dev assumptions to release defaults

The extension should prefer the packaged server path in normal use while preserving local checkout overrides for development.

- [ ] Default server bootstrap to pinned `uvx --from ... memento-workflow-server`
  Use the shipped server entrypoint and pinned source/tag as the normal bootstrap path, while leaving `MEMENTO_WORKFLOW_DIR` or explicit config overrides available for local development.

- [ ] Pass configured process env and cwd consistently
  Ensure `server.command`, `server.args`, `server.cwd`, and `server.env` from `memento` config fully control backend startup when present.

<!-- accept -->
- In the default path, `memento-pi` can launch the packaged backend server without a manually started Python process.
- Explicit `memento.server` config overrides still take precedence for development or custom deployments.
- Configured backend env and cwd are applied consistently when spawning the server.
<!-- /accept -->
<!-- /task -->

<!-- task -->
### Refresh README and config docs to current reality

The current public docs still reflect an earlier scaffold state and need to match the implemented runtime behavior.

- [ ] Document actual install/use flow
  Update README to describe the implemented command surfaces (`/wf`, `/mw`, native skill path), backend bootstrap modes, and `.pi/settings.json` `memento` config.

- [ ] Document model alias and thinking-level configuration
  Show both string aliases and object-form aliases with `thinkingLevel`, and explain that provider-specific wire mappings are delegated to pi/provider configuration.

- [ ] Refresh rollout checklist items that are already done
  Mark completed items or replace them with follow-up tasks so future sessions are not forced to rediscover what already landed.

<!-- accept -->
- README no longer describes the extension as a shape-only scaffold when the runtime is already functional.
- Documentation explains how to configure model aliases and per-alias thinking levels under `.pi/settings.json` `memento`.
- The rollout checklist reflects current implementation state instead of stale aspirational backlog items.
<!-- /accept -->
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- Release defaults must be pinned and explicit rather than floating to HEAD.
- Do not remove local development overrides; document them as such.
- Keep docs aligned with the actual implemented runtime, not a future idealized architecture.
<!-- /constraints -->

## Implementation Notes

The extension README is currently out of date relative to the code. Treat that drift as a rollout bug, not a nice-to-have cleanup.

## Verification

<!-- verification -->
```bash
cd memento-pi && npm run typecheck
cd memento-pi && npm run test:integration
```
<!-- /verification -->

## Context

<!-- context:inline -->
This step is the remaining release-facing portion of the original P0 work: the backend server entrypoint exists, but the extension bootstrap defaults and user docs still need to reflect the intended packaged story.
<!-- /context:inline -->

<!-- context:files -->
- memento-pi/memory/pi-rollout-plan.md
- memento-pi/memory/pi-rollout-checklist.md
- memento-pi/README.md
- memento-pi/memory/runtime-notes.md
<!-- /context:files -->

## Starting Points

<!-- starting_points -->
- memento-pi/src/server-bootstrap.ts
- memento-pi/src/client.ts
- memento-pi/src/config.ts
- memento-pi/README.md
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] memento-pi/memory/pi-rollout-checklist.md
- [ ] memento-pi/memory/runtime-notes.md
- [ ] memento-pi/README.md
