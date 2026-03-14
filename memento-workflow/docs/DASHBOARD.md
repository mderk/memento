# Workflow Dashboard

Local web UI and CLI for browsing workflow runs, viewing step output and artifacts, and comparing runs.

## Architecture

```
Browser (localhost:PORT)           Starlette API (localhost:PORT)
┌──────────────────────┐           ┌───────────────────────┐
│  Vite + React/TS     │ ──API───▸ │  /api/runs            │
│  SPA with routing    │           │  /api/runs/:id        │──▸ .workflow-state/
│  WebSocket client    │ ◂──WS───▸ │  /api/ws              │     ├── <run_id>/
└──────────────────────┘           └───────────────────────┘     │   ├── meta.json
                                                                 │   ├── state.json
CLI client ─────────────────────▸ dashboard.data (direct reads)  │   ├── artifacts/
                                                                 │   └── children/
```

- **Web server**: Starlette + uvicorn (explicit dependencies in `pyproject.toml`)
- **Frontend**: React SPA built with Vite, served as static files from `frontend/dist/`
- **CLI client**: Direct filesystem reads via `dashboard.data`, no running server needed
- **Data layer**: Read-only. Scans `.workflow-state/<run_id>/` directories

### Requirements

- Python 3.10+
- Node.js 18+ (only for frontend development/building, not for serving pre-built frontend)

## Quick Start

### CLI (no server needed)

```bash
cd memento-workflow

# List all runs
python -m dashboard.cli --cwd /path/to/project runs

# Show run detail (prefix match supported)
python -m dashboard.cli --cwd /path/to/project run ce71e

# View artifact content
python -m dashboard.cli --cwd /path/to/project artifact ce71e check-context/result.json

# Dump steps as JSON
python -m dashboard.cli --cwd /path/to/project steps ce71e

# Diff two runs
python -m dashboard.cli --cwd /path/to/project diff aaa111 bbb222
```

### Web Server

```bash
cd memento-workflow

# Auto-select port, open browser
python -m dashboard.cli --cwd /path/to/project serve

# Specific port
python -m dashboard.cli --cwd /path/to/project serve --port 8787

# Remote access (bind all interfaces)
python -m dashboard.cli --cwd /path/to/project serve --host 0.0.0.0 --port 8787

# Without opening browser
python -m dashboard.cli --cwd /path/to/project serve --no-open
```

Alternative entry point (equivalent, no browser open):

```bash
python -m dashboard --cwd /path/to/project --port 8787
```

### MCP Tool

From Claude Code, call the `open_dashboard` tool with `cwd` set to the project directory. The server starts on an auto-selected port and opens the browser.

## CLI Reference

```
python -m dashboard.cli [--cwd DIR] COMMAND
```

| Command | Arguments | Description |
|---------|-----------|-------------|
| `runs` | — | List all runs with status, workflow, timestamps, step count |
| `run` | `<run_id>` | Show run detail: meta + step list with hierarchy |
| `steps` | `<run_id>` | Dump steps as JSON (for programmatic use) |
| `artifact` | `<run_id> <path>` | Print artifact file content to stdout |
| `diff` | `<id1> <id2>` | Diff two runs by matching steps on `results_key` |
| `serve` | `[--port] [--host] [--no-open]` | Start the web server |

Run IDs support prefix matching — `ce71e` resolves to `ce71e112b6e5` if unambiguous.

## API Reference

All endpoints are prefixed with `/api/`.

### `GET /api/info`

Returns project metadata.

```json
{"project": "minerals2", "cwd": "/path/to/project"}
```

### `GET /api/runs`

Lists all runs with nested children.

```json
[
  {
    "run_id": "ce71e112b6e5",
    "workflow": "update-environment",
    "status": "completed",
    "started_at": "2026-03-13T02:30:05+00:00",
    "completed_at": "2026-03-13T02:44:06+00:00",
    "step_count": 84,
    "cwd": "/path/to/project",
    "parent_run_id": null,
    "child_run_ids": ["97eebd18ee35"],
    "children": [
      {
        "run_id": "97eebd18ee35",
        "workflow": "",
        "status": "completed",
        "children": []
      }
    ]
  }
]
```

### `GET /api/runs/{run_id}`

Returns full run detail: meta, ordered steps, and artifact tree.

```json
{
  "meta": { "run_id": "...", "workflow": "...", "status": "...", "step_count": 10 },
  "steps": [
    {
      "exec_key": "check-context",
      "results_key": "check-context",
      "name": "check-context",
      "status": "success",
      "output_preview": "{\"exists\": true}",
      "duration": 0.037,
      "error": null,
      "cost_usd": null,
      "order": 1,
      "artifact_files": ["command.txt", "output.txt", "result.json"]
    }
  ],
  "artifact_tree": [
    {
      "name": "check-context",
      "path": "check-context",
      "type": "directory",
      "children": [
        {"name": "output.txt", "path": "check-context/output.txt", "type": "file", "size": 42}
      ]
    }
  ]
}
```

For child runs, inherited parent steps are automatically excluded — only the child's own steps are returned.

### `GET /api/runs/{run_id}/artifacts/{path}`

Returns artifact file content. Content-Type is set based on extension (`.json`, `.md`, or `text/plain`). Path traversal is blocked.

### `GET /api/diff/{id1}/{id2}`

Compares two runs by matching steps on `results_key`.

```json
{
  "run1": { "run_id": "...", "status": "..." },
  "run2": { "run_id": "...", "status": "..." },
  "diffs": [
    {
      "results_key": "check-context",
      "change": "modified",
      "left": { "exec_key": "...", "status": "success" },
      "right": { "exec_key": "...", "status": "failure" },
      "artifact_diffs": [
        {"file": "output.txt", "diff": "--- id1/output.txt\n+++ id2/output.txt\n..."}
      ]
    },
    {
      "results_key": "new-step",
      "change": "added",
      "right": { "exec_key": "...", "status": "success" }
    }
  ]
}
```

Change types: `added`, `removed`, `modified`, `unchanged`.

### `WebSocket /api/ws`

Pushes run list changes every 2 seconds.

```json
{"type": "run_new", "run": { "run_id": "...", ... }}
{"type": "run_update", "run": { "run_id": "...", ... }}
{"type": "run_removed", "run_id": "abc123"}
```

### Shutdown Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/shutdown` | POST | Immediate shutdown (close button) |
| `/api/tab-closed` | POST | Schedules shutdown after 3s (tab close) |
| `/api/cancel-shutdown` | POST | Cancels pending shutdown (page reload) |

Tab close vs refresh: browser fires `pagehide` → sends beacon to `/api/tab-closed` → 3s grace. On refresh, the reloaded page sends `/api/cancel-shutdown` within that window.

## Web Frontend

Three pages:

### Run List (`/`)

Table of all workflow runs with:
- Sortable columns: workflow, status, date/time, steps
- Status filter: all / running / completed / error / cancelled
- Tree display of parent/child runs (expand/collapse)
- Live updates via WebSocket
- Select two runs → Compare button → diff view

### Run Detail (`/runs/:id`)

Compact header with workflow name, status, timestamps, duration, step count.

Two-panel layout:
- **Left sidebar**: Step timeline with hierarchy (indented by exec_key depth), status dots, durations, artifact file counts
- **Right panel**: Step output preview + artifact file tabs (click to load content)

Auto-refreshes every 3s while run status is `running`.

### Run Diff (`/diff/:id1/:id2`)

Side-by-side comparison:
- Steps matched by `results_key`
- Change indicators: added (+), removed (-), modified (~), unchanged (=)
- Expandable unified diff for modified artifacts
- Toggle to show/hide unchanged steps

## Data Directory Structure

The dashboard reads from `.workflow-state/` in the project directory:

```
.workflow-state/
├── <run_id>/
│   ├── meta.json          # {run_id, workflow, cwd, status, started_at, completed_at}
│   ├── state.json         # Checkpoint: {ctx: {results_scoped: {...}}, ...}
│   ├── artifacts/
│   │   ├── step-name/
│   │   │   ├── output.txt
│   │   │   ├── result.json
│   │   │   └── command.txt
│   │   └── loop-name/0/step-name/
│   │       └── output.txt
│   └── children/
│       └── <child_run_id>/
│           ├── meta.json
│           ├── state.json
│           └── artifacts/
```

- `meta.json`: Written at run start and completion. Source of truth for workflow name and timestamps.
- `state.json`: Engine checkpoint. Contains `ctx.results_scoped` — a dict of step results keyed by `exec_key`.
- `artifacts/`: Step outputs, organized by `exec_key` converted to a path (type prefixes stripped, `[i=N]` → `/N`).
- `children/`: Sub-runs spawned by parallel blocks. Each has its own state and artifacts.

Child runs inherit parent's `results_scoped` in their `state.json`. The dashboard filters these out by comparing with the parent's keys, showing only the child's own steps.

## File Structure

```
dashboard/
├── __init__.py
├── __main__.py       # python -m dashboard entry point
├── app.py            # Starlette app factory, static file serving
├── api.py            # Route handlers, WebSocket, shutdown coordination
├── cli.py            # CLI client + serve command
├── data.py           # Data layer: list_runs, get_run_detail, diff_runs, ...
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── index.html
    └── src/
        ├── main.tsx
        ├── App.tsx           # Shell: header, close button, tab-close handling
        ├── api.ts            # Fetch wrappers + WebSocket client
        ├── types.ts          # TypeScript interfaces
        ├── app.css           # Theme: "Terminal Noir"
        ├── pages/
        │   ├── RunList.tsx
        │   ├── RunDetail.tsx
        │   └── RunDiff.tsx
        └── components/
            ├── StatusBadge.tsx
            └── Timeline.tsx
```

## Development

### Frontend dev server (hot reload)

```bash
cd dashboard/frontend
npm install
npm run dev          # starts Vite on :5173, proxies /api to :8787
```

In another terminal:

```bash
python -m dashboard --cwd /path/to/project --port 8787
```

### Building frontend for production

```bash
cd dashboard/frontend
npm run build        # outputs to dist/
```

The Starlette server serves `frontend/dist/` as static files automatically.

### Running tests

```bash
cd memento-workflow
uv run pytest tests/test_dashboard.py -v
```

Tests cover the data layer (list_runs, get_run_detail, artifact reading, path traversal blocking, diffing) and the CLI (all commands, prefix matching, child step filtering).
