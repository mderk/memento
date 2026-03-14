---
name: dashboard
description: Open the workflow dashboard to browse runs, view artifacts, and compare workflow executions
version: 1.0.0
---

# Workflow Dashboard

Open the local web dashboard to browse workflow runs, inspect step timelines, view artifacts, and diff between runs.

Call `mcp__plugin_memento-workflow_memento-workflow__open_dashboard` with:

- `cwd`: the project directory containing `.workflow-state/` (defaults to `.`)
- `port`: port for the dashboard server (defaults to `8787`)

This starts a local web server and opens the dashboard in the browser. If the server is already running, it just opens the browser.

The dashboard shows:

- **Run list** — all workflow runs with status, duration, step count
- **Run detail** — step timeline with output preview, artifact tree with file viewer
- **Run diff** — side-by-side comparison of two runs, matching steps by name

The dashboard auto-updates via WebSocket when workflows are running.
