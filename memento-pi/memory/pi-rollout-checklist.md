# pi rollout checklist

Execution checklist derived from `pi-rollout-plan.md`.

## P0a — dev dogfood for protocol workflows

### `memento-pi`
- [ ] add protocol command helpers
  - [ ] resolve protocol dir from number/path/description
  - [ ] share helper logic between protocol wrappers
- [ ] add `/mw create-protocol`
  - [ ] resolve/create `protocol_dir`
  - [ ] derive `prd_source`
  - [ ] call `start(workflow="create-protocol", ...)`
- [ ] add `/mw process-protocol [arg]`
  - [ ] resolve protocol dir from id/path/description
  - [ ] verify `plan.md`
  - [ ] inspect `.last_run`
  - [ ] ask user resume/fresh
  - [ ] call `start(workflow="process-protocol", variables={protocol_dir}, resume=...)`
- [ ] keep current dev bootstrap
  - [ ] local `pi install -l`
  - [ ] local `MEMENTO_WORKFLOW_DIR` fallback
  - [ ] no `.pi/settings.json` migration required for dogfood

Acceptance:
- [ ] `/mw create-protocol ...` works on a real local project
- [ ] `/mw process-protocol ...` works on a real local project
- [ ] `.last_run` resume/fresh flow works
- [ ] existing Claude/Codex/Cursor skill layer remains unchanged

## P0 — backend packaging + generic workflow UX

### `memento-workflow`
- [ ] `pyproject.toml`
  - [ ] add console script: `memento-workflow-server = "scripts.server:main"`
- [ ] `scripts/runner.py`
  - [ ] add public `resume(run_id, cwd, workflow_dirs=[])`
  - [ ] load checkpoint metadata / workflow name server-side
  - [ ] return resumed action envelope matching other JSONL methods
- [ ] `scripts/server.py`
  - [ ] register new `resume` method in `METHODS`
- [ ] `README.md`
  - [ ] document `memento-workflow-server`
  - [ ] document runtime env vars used by server/process

Acceptance:
- [ ] `uvx ... memento-workflow-server` starts and answers `list_workflows`
- [ ] `resume(run_id, cwd, workflow_dirs)` works without workflow name from caller

### `memento-pi`
- [ ] `src/config.ts`
  - [ ] migrate config loading to `.pi/settings.json` top-level `memento` section
  - [ ] support `server.command`
  - [ ] support `server.args`
  - [ ] support `server.env`
  - [ ] support `server.cwd`
  - [ ] support `workflowDirs`
  - [ ] keep model alias settings support
- [ ] `src/server-bootstrap.ts`
  - [ ] read server config from `getConfig()`
  - [ ] default bootstrap to pinned `uvx --from git+... memento-workflow-server`
  - [ ] keep `MEMENTO_WORKFLOW_DIR` fallback for development only
- [ ] `src/client.ts`
  - [ ] pass configured env into `spawn(...)`
- [ ] `src/index.ts`
  - [ ] add `/wf resume <run_id>`
  - [ ] call backend `resume(...)`
  - [ ] pass configured `workflowDirs` to `list/start/resume`
- [ ] `README.md`
  - [ ] document release-mode install
  - [ ] document dev-mode local checkout fallback
  - [ ] document `.pi/settings.json` config shape

Acceptance:
- [ ] `/wf list` works without manual backend start
- [ ] `/wf start development` works in repo with `.workflows/`
- [ ] `/wf resume <run_id>` works
- [ ] config is read from `.pi/settings.json`

## P1 — wrapper commands

### command namespace
- [ ] reserve `/mw` for workflow wrappers
- [ ] keep `/wf` for generic workflow control only

### `memento-pi`
- [ ] create `src/commands/` folder if needed
- [ ] add `/mw develop <task>`
  - [ ] validate non-empty task
  - [ ] call `start(workflow="development", variables={task})`
- [ ] add `/mw process-protocol [arg]`
  - [ ] resolve protocol dir from id/path/description
  - [ ] verify `plan.md`
  - [ ] inspect `.last_run`
  - [ ] ask user resume/fresh
  - [ ] call `start(workflow="process-protocol", variables={protocol_dir}, resume=...)`
- [ ] add `/mw merge-protocol [arg]`
  - [ ] resolve protocol dir
  - [ ] call `start(workflow="merge-protocol", variables={protocol_dir})`
- [ ] add `/mw commit`
- [ ] add `/mw code-review`
- [ ] add `/mw testing`
- [ ] add `/mw verify-fix`
- [ ] add `/mw create-protocol`

Acceptance:
- [ ] `/mw develop ...` works on real project
- [ ] `/mw process-protocol ...` works with `.last_run` resume prompt
- [ ] existing Claude/Codex/Cursor skill layer remains unchanged

## P2 — optional `memento` environment wrappers

- [ ] identify distribution/source for `memento/skills/create-environment`
- [ ] identify distribution/source for `memento/skills/update-environment`
- [ ] decide how `plugin_root` is resolved in pi world
- [ ] decide how `plugin_version` is resolved in pi world
- [ ] add workflowDirs/config for those workflow packs
- [ ] add `/mw create-environment`
- [ ] add `/mw update-environment`

## Tests

### `memento-workflow`
- [ ] packaged server smoke test
- [ ] `resume(...)` integration test

### `memento-pi`
- [ ] `/mw create-protocol` integration test
- [ ] `/mw process-protocol` integration test
- [ ] config parsing test for `.pi/settings.json`
- [ ] backend bootstrap test
- [ ] `/wf resume` integration test
- [ ] `/mw develop` integration test
- [ ] full existing integration suite stays green
