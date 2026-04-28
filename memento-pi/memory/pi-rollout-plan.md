# pi rollout plan

Goal: make `memento-pi` usable on real projects with real workflows, without changing the existing Claude/Codex/Cursor layer.

## Scope / non-scope

In scope:
- run existing project workflows from `cwd/.workflows/` in pi
- run bundled engine workflows (`memento-workflow/skills/*`)
- add pi-native commands for common workflow entrypoints
- package/bootstrap the Python server so users do not manage it manually

Out of scope for this rollout:
- rewriting `.claude/skills/*`
- changing `.workflows/*` DSL or layout
- porting the `memento` environment-generation/update layer in the first pass
- replacing the Claude/Codex/Cursor runtime model

## Target user experience

Install once:
- install `memento-pi` into pi
- no manual server start
- no manual relay protocol
- no manual checkout/path config in the normal released setup

Use in a project:
- open repo containing `.workflows/`
- run `/wf list` or `/mw develop ...` or `/mw process-protocol ...`
- extension auto-starts backend, drives workflow, shows UI for `ask_user`, hands off inline prompts, and auto-runs relay/parallel children

## Hard decisions for this rollout

1. Config source: move to pi's `.pi/settings.json` under top-level `memento`.
2. Resume API: add dedicated backend method `resume(run_id, cwd, workflow_dirs=[])` so pi does not need the workflow name.
3. Command namespace: keep generic workflow control under `/wf ...`; put wrapper commands under `/mw ...` to avoid collisions.
4. Distribution model:
   - dev mode: local path install + explicit local backend path fallback is allowed
   - release mode: `memento-pi` launches backend via `uvx` from a pinned Git source

## Architecture boundary

Keep unchanged:
- `.claude/skills/**` — still used by Claude/Codex/Cursor
- `.workflows/**` — shared workflow source of truth
- `memento-workflow` engine logic and checkpoint format except normal bugfixes

Add pi-only layer:
- `memento-pi` owns runtime orchestration and wrapper commands
- later, optional pi wrappers for `memento` environment workflows

## Phase plan

### P0: backend packaging + generic workflow UX
1. package `memento-workflow` server as a callable CLI
2. add backend `resume(run_id, cwd, workflow_dirs=[])`
3. make `memento-pi` spawn that server from config/defaults
4. move `memento-pi` config to `.pi/settings.json`
5. add config for extra workflow dirs
6. add `/wf resume <run_id>`
7. keep `.workflows/` unchanged

### P1: pi-native wrapper commands for existing project workflows
Add wrapper subcommands under `/mw`:
- `/mw develop <task>`
- `/mw process-protocol [id|path|description]`
- `/mw merge-protocol [id|path|description]`
- `/mw commit`
- `/mw code-review`
- `/mw testing`
- `/mw verify-fix`
- `/mw create-protocol`

These commands do only pre-start logic and call the existing workflows. They do not implement relay.

### P2: pi wrappers for `memento` environment workflows
Use existing workflow definitions in:
- `memento/skills/create-environment/workflow.py`
- `memento/skills/update-environment/workflow.py`

Add pi commands later, after P0/P1 are stable.

## Concrete implementation backlog

### A. `memento-workflow`

| File | Change | Why | Priority |
|---|---|---|---|
| `pyproject.toml` | add CLI script, e.g. `memento-workflow-server = "scripts.server:main"` | lets pi run server without checkout-path assumptions | P0 |
| `scripts/runner.py` + `scripts/server.py` | add backend method `resume(run_id, cwd, workflow_dirs=[])` that loads checkpoint metadata and resumes without requiring workflow name from the caller | makes `/wf resume <run_id>` possible and removes pi-side guesswork | P0 |
| `README.md` | document server entrypoint + env vars | installation story | P0 |

Notes:
- v1 may still support `python -m scripts.server`
- no DSL changes required

### B. `memento-pi` core bootstrap/config

| File | Change | Why | Priority |
|---|---|---|---|
| `src/server-bootstrap.ts` | read `memento.server.command/args/env/cwd` from `.pi/settings.json`; default to packaged/`uvx` bootstrap; keep `MEMENTO_WORKFLOW_DIR` as dev fallback only | no manual backend start/path editing in normal use | P0 |
| `src/config.ts` | extend config schema to include `server` and `workflowDirs`; migrate from `memento-pi.json` to `.pi/settings.json` top-level `memento` section | central config source, consistent with pi conventions | P0 |
| `src/client.ts` | support per-process env overrides if not already | needed for backend runtime flags | P0 |
| `README.md` | document install/bootstrap modes | user-facing setup | P0 |

Release-mode default bootstrap:
- command: `uvx`
- args: `--from git+https://github.com/mderk/memento@<tag>#subdirectory=memento-workflow memento-workflow-server`

Rules:
- released `memento-pi` should pin a specific tag/version, not default to floating HEAD
- override via `.pi/settings.json` is allowed for dev/custom setups
- local checkout/path mode via `MEMENTO_WORKFLOW_DIR` remains supported for development only

### C. `memento-pi` generic workflow commands

| File | Change | Why | Priority |
|---|---|---|---|
| `src/index.ts` | add `/wf resume <run_id>` | required for resumable real workflows | P0 |
| `src/index.ts` | pass configured `workflowDirs` to `list/start/resume` calls | discover external workflow packs | P0 |
| `src/index.ts` | keep `/wf list/start/status/cancel/reload` as stable generic surface | generic entrypoint for all workflows | P0 |

Resume behavior:
- `/wf resume <run_id>` calls backend `resume(run_id, cwd, workflow_dirs)`
- backend owns checkpoint lookup + workflow-name resolution
- extension does not parse checkpoint files itself

### D. `memento-pi` wrapper commands for existing project workflows

| Command | Input | Pre-start logic | Backend call | Priority |
|---|---|---|---|---|
| `/mw develop <task>` | free text task | validate non-empty | `start(workflow="development", variables={task})` | P1 |
| `/mw process-protocol [arg]` | id/path/description | resolve protocol dir, inspect `.last_run`, ask resume/fresh | `start(workflow="process-protocol", variables={protocol_dir}, resume=...)` | P1 |
| `/mw merge-protocol [arg]` | id/path/description | resolve protocol dir | `start(workflow="merge-protocol", variables={protocol_dir})` | P1 |
| `/mw commit` | optional args later | maybe infer workdir/current repo state | `start(workflow="commit", variables={...})` | P1 |
| `/mw code-review` | optional args later | maybe infer review scope | `start(workflow="code-review", variables={...})` | P1 |
| `/mw testing` | optional args later | map CLI args to variables | `start(workflow="testing", variables={...})` | P1 |
| `/mw verify-fix` | optional args later | map CLI args to variables | `start(workflow="verify-fix", variables={...})` | P1 |
| `/mw create-protocol` | free text/topic | validate args | `start(workflow="create-protocol", variables={...})` | P1 |

Implementation note:
- if command glue grows, move wrappers from `src/index.ts` into `src/commands/*.ts`

### E. Specific command details

#### `/mw process-protocol`
Logic:
1. resolve protocol dir from arg:
   - number like `3` / `003`
   - explicit path
   - description match against `.protocols/*/plan.md`
2. verify `plan.md` exists
3. if `<protocol_dir>/.last_run` exists, ask user whether to resume
4. call existing `process-protocol` workflow

Preferred implementation split:
- `src/commands/protocols.ts` for resolution helpers
- UI prompt via `ctx.ui.select` / `confirm`

#### `/mw develop`
Logic:
1. require non-empty task string
2. start existing `development` workflow with `{ task }`

### F. `memento` environment workflows (later)

Do not block P0/P1 on this.

When ready:
- add configured workflow dirs pointing at `memento/skills/create-environment` and `memento/skills/update-environment`
- add commands:
  - `/memento create-environment`
  - `/memento update-environment`
- pass variables:
  - `plugin_root`
  - `plugin_version`

Open question to resolve before P2:
- whether `plugin_root` should come from installed package metadata/path, or from explicit config

## Config shape

Target `.pi/settings.json` shape:

```json
{
  "extensions": ["/abs/path/to/memento-pi"],
  "memento": {
    "server": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/mderk/memento@<tag>#subdirectory=memento-workflow",
        "memento-workflow-server"
      ],
      "env": {
        "MEMENTO_SANDBOX": "auto",
        "MEMENTO_PARALLEL_AUTO_ADVANCE": "on",
        "WORKFLOW_DEBUG": "0"
      }
    },
    "workflowDirs": [
      "/abs/path/to/extra/workflows"
    ]
  }
}
```

Rules:
- packaged bootstrap is default
- local checkout/path bootstrap remains supported for development
- project `.workflows/` are always auto-discovered by the backend from `cwd`
- release builds should pin a tag/version for backend bootstrap
- explicit config override can replace the default source/pin

## Installation model

| Component | Dev mode | Release mode |
|---|---|---|
| `memento-pi` | `pi install -l /abs/path/to/memento-pi` | install as a normal pi package |
| backend server | local checkout via `MEMENTO_WORKFLOW_DIR` fallback | auto-fetched/launched by `uvx` from pinned Git source |

User should not manually start the backend server in release mode.

## Acceptance criteria

P0 done when:
- user can install `memento-pi` and run `/wf list` without manually starting backend
- user can run `/wf start development` in a repo with `.workflows/`
- user can `/wf resume <run_id>`
- no manual relay protocol is required
- config is read from `.pi/settings.json` `memento` section

P1 done when:
- `/mw develop ...` works on a real project
- `/mw process-protocol ...` works including resume/fresh prompt using `.last_run`
- existing Claude/Codex/Cursor skills still work unchanged

## Test backlog

| Area | Test |
|---|---|
| backend packaging | spawn packaged server entrypoint and call `list_workflows` |
| backend resume API | create run, checkpoint it, call `resume(run_id, cwd, workflow_dirs)` |
| config | parse `.pi/settings.json` `memento.server` and `workflowDirs` |
| generic pi UX | `/wf list`, `/wf start`, `/wf resume` integration |
| wrapper commands | `/mw develop` integration |
| wrapper commands | `/mw process-protocol` path resolution + `.last_run` resume prompt |
| regression | existing `memento-pi` integration suite remains green |

## Recommended order of execution

1. `memento-workflow` server CLI
2. backend `resume(run_id, cwd, workflow_dirs)`
3. `memento-pi` config migration to `.pi/settings.json`
4. `memento-pi` server bootstrap config
5. `memento-pi` `workflowDirs`
6. `memento-pi` `/wf resume`
7. `memento-pi` `/mw develop`
8. `memento-pi` `/mw process-protocol`
9. remaining wrapper commands
10. optional P2 `memento` environment wrappers
