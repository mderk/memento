---
id: 02-p0-backend-packaging-and-generic-workflow-ux-01-package-the-workflow-server-entrypoint
status: pending
estimate: 1h30m
---
# Package the workflow server entrypoint

## Objective

<!-- objective -->
Make the `memento-workflow` backend invokable as a stable CLI so pi can launch it without relying on a checked-out repo layout. This is the packaging foundation for release-mode bootstrap.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Expose a supported server CLI

Release-mode pi installs need a deterministic command they can spawn directly.

- [ ] Add and verify a console entrypoint for the server
  Publish `memento-workflow-server = "scripts.server:main"` (or equivalent) in package metadata so `uvx` and package installs can launch the backend the same way.

- [ ] Keep backwards-compatible developer entrypoints where helpful
  If `python -m scripts.server` or other dev paths are already in use, keep them working while documenting the new supported entrypoint.

<!-- accept -->
- A packaged install exposes `memento-workflow-server` as an executable entrypoint.
- The server entrypoint starts successfully in a clean environment without assuming a repo checkout path.
- Existing developer bootstrap paths continue to work during the rollout.
<!-- /accept -->
<!-- /task -->

<!-- task -->
### Document server bootstrap expectations

The bootstrap contract should be explicit before the pi extension starts depending on it.

- [ ] Document server startup commands and runtime environment variables
  Update backend documentation so pi-side bootstrap code has a clear reference for supported command lines and env knobs.

- [ ] Add a smoke test for packaged startup
  Verify that the packaged server can start and answer a simple request such as `list_workflows`.

<!-- accept -->
- Backend documentation shows the supported server entrypoint and the env vars needed at runtime.
- A smoke test proves the packaged server can start and respond to `list_workflows`.
- pi-side bootstrap work can consume the documented contract without repo-specific assumptions.
<!-- /accept -->
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- Do not change the workflow DSL or checkpoint format as part of packaging.
- Preserve the current MCP/server behavior aside from the new supported entrypoint and related bugfixes.
- Keep packaging changes narrowly focused on startup and documentation.
<!-- /constraints -->

## Implementation Notes

Although this is backend work, keep the consumer in mind: `memento-pi` will eventually default to a pinned `uvx --from git+... memento-workflow-server` bootstrap. The command contract must therefore be stable and documented.

## Verification

<!-- verification -->
```bash
cd memento-workflow && uv run pytest
cd memento-workflow && uv run pyright
```
<!-- /verification -->

## Context

<!-- context:inline -->
This step corresponds to backlog item A in the rollout plan. It is intentionally limited to packaging and startup, not wrapper UX.
<!-- /context:inline -->

<!-- context:files -->
- memento-pi/memory/pi-rollout-plan.md
- .memory_bank/tech_stack.md
<!-- /context:files -->

## Starting Points

<!-- starting_points -->
- memento-workflow/pyproject.toml
- memento-workflow/scripts/server.py
- memento-workflow/README.md
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] .memory_bank/tech_stack.md
- [ ] memento-pi/memory/pi-rollout-checklist.md
