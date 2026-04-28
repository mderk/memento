---
id: 02-p0-backend-packaging-and-generic-workflow-ux-03-migrate-config-and-bootstrap-to-pisettingsjson
status: pending
estimate: 3h
---
# Migrate config and bootstrap to `.pi/settings.json`

## Objective

<!-- objective -->
Give `memento-pi` a pi-native configuration source for backend startup and extra workflow directories, while preserving local development overrides during the rollout. This turns backend startup from a manual dev trick into a supported product path.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Extend config loading for the `memento` section

Config should follow pi conventions while retaining safe compatibility for current local setups.

- [ ] Load `memento.server` and `memento.workflowDirs` from `.pi/settings.json`
  Support `server.command`, `server.args`, `server.env`, `server.cwd`, and `workflowDirs`, while keeping model alias settings and legacy fallback behavior where still required.

- [ ] Define precedence between new config, legacy files, and dev fallbacks
  Make override order explicit so users can reason about why a given backend command is being launched.

<!-- accept -->
- `memento-pi` reads backend startup settings from the top-level `memento` section in `.pi/settings.json`.
- Configured `workflowDirs` are available to the command layer after config load.
- Legacy/dev fallback behavior remains available where intended and does not silently override explicit `.pi/settings.json` values.
<!-- /accept -->
<!-- /task -->

<!-- task -->
### Bootstrap the backend from config/defaults

Release mode should be zero-manual-start, while development mode still supports local iteration.

- [ ] Read bootstrap config in `server-bootstrap` and `client`
  Use configured command/args/env/cwd when spawning the backend process, including environment overrides needed by runtime flags.

- [ ] Default to pinned `uvx` release bootstrap
  Use a pinned Git/tag source for `memento-workflow-server` in the default path, and keep `MEMENTO_WORKFLOW_DIR` as a development-only fallback.

- [ ] Document install/bootstrap modes for users and contributors
  Explain release-mode setup, local path install, and how to override backend startup safely.

<!-- accept -->
- Without manually starting the backend, a configured install can launch `memento-workflow-server` from `memento-pi`.
- Configured environment variables are passed through to the backend process.
- Documentation explains release-mode defaults, development fallback, and config override shape clearly enough for a new contributor to reproduce setup.
<!-- /accept -->
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- Use `.pi/settings.json` as the primary config source for release-mode behavior.
- Pin the default release bootstrap source/version instead of using floating HEAD.
- Keep local checkout/path mode available only as an explicit development fallback.
<!-- /constraints -->

## Implementation Notes

This step implements backlog item B from the rollout plan. Keep configuration parsing and process spawning separate so tests can validate schema/precedence without launching real processes.

## Verification

<!-- verification -->
```bash
cd memento-pi && npm run typecheck
cd memento-pi && npm run test:integration
```
<!-- /verification -->

## Context

<!-- context:inline -->
The rollout plan moves config ownership to `.pi/settings.json` specifically to align with pi conventions and eliminate manual backend start steps in normal use.
<!-- /context:inline -->

<!-- context:files -->
- memento-pi/memory/pi-rollout-plan.md
- memento-pi/memory/runtime-notes.md
- memento-pi/memory/stabilization-plan-v2.md
<!-- /context:files -->

## Starting Points

<!-- starting_points -->
- memento-pi/src/config.ts
- memento-pi/src/server-bootstrap.ts
- memento-pi/src/client.ts
- memento-pi/README.md
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] memento-pi/memory/pi-rollout-checklist.md
- [ ] memento-pi/memory/runtime-notes.md
- [ ] memento-pi/README.md
