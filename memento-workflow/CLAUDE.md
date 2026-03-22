# Memento Workflow — Developer Guide

Stateful workflow engine MCP server for multi-step automation. Executes imperative workflows defined as Python dataclasses with checkpoint/resume, interactive prompts, and parallel execution.

## Directory Structure

```
memento-workflow/
├── serve.py                     # MCP entry point
├── scripts/                     # Engine implementation
│   ├── runner.py                # FastMCP server tools + run management
│   ├── utils.py                 # Template substitution, condition evaluation
│   ├── engine/                  # State machine and block execution
│   │   ├── types.py             # Block type definitions, WorkflowContext
│   │   ├── protocol.py          # Action response models (Pydantic)
│   │   ├── core.py              # Frame, RunState
│   │   ├── state.py             # State machine: advance(), apply_submit()
│   │   ├── actions.py           # Action builders
│   │   ├── parallel.py          # ParallelEachBlock execution
│   │   ├── subworkflow.py       # SubWorkflow block handling
│   │   └── child_runs.py        # Child run creation and management
│   └── infra/                   # Infrastructure and I/O
│       ├── checkpoint.py        # Durable checkpoint save/load
│       ├── compiler.py          # YAML workflow compiler
│       ├── loader.py            # Workflow discovery and loading
│       ├── sandbox.py           # OS-level sandboxing (Seatbelt/bubblewrap)
│       ├── shell_exec.py        # Shell command execution
│       └── artifacts.py         # Artifact persistence
├── dashboard/                   # Web UI and CLI for browsing workflow state
│   ├── __main__.py              # python -m dashboard entry point
│   ├── app.py                   # Starlette app factory
│   ├── api.py                   # API routes + WebSocket + shutdown
│   ├── cli.py                   # CLI client: runs, run, steps, artifact, diff, serve
│   ├── data.py                  # Data layer (read-only .workflow-state/ scanner)
│   └── frontend/                # React + Vite SPA
├── skills/
│   ├── workflow-engine/SKILL.md # Relay protocol documentation
│   ├── dashboard/SKILL.md       # Dashboard MCP skill
│   └── test-workflow/           # Educational demo workflow
├── docs/
│   ├── DESIGN.md                # Architecture and protocol spec
│   ├── YAML-DSL.md              # YAML workflow format reference
│   └── DASHBOARD.md             # Dashboard: API, CLI, web UI reference
└── tests/                       # Engine test suite
```

## Development

### Running tests

```bash
# From this directory
uv run pytest

# From repo root (runs all tests)
cd .. && uv run pytest
```

### Key concepts

- **ENGINE_ROOT**: `Path(__file__).resolve().parents[1]` from `scripts/runner.py` — points to `memento-workflow/`
- **Workflow discovery**: scans `ENGINE_ROOT/skills/*/workflow.py`, project `.workflows/`, and explicit `workflow_dirs`
- **Relay protocol**: Claude Code acts as relay, calling MCP tools (`start`, `submit`, `next`, `cancel`)

### Security

- `serve.py` re-execs inside OS sandbox (Seatbelt on macOS, bubblewrap on Linux) — restricts writes to `cwd` + `/tmp` for the entire process
- `MEMENTO_SANDBOX=off` disables sandboxing (for containers/CI)
- See `docs/DESIGN.md` Security section for full threat model

### Dashboard

Web UI and CLI for browsing workflow runs, viewing artifacts, and comparing runs. See `docs/DASHBOARD.md` for full reference.

```bash
# CLI (no server needed)
python -m dashboard.cli --cwd /path/to/project runs
python -m dashboard.cli --cwd /path/to/project run <id>

# Web server
python -m dashboard.cli --cwd /path/to/project serve --port 8787
```

### Architecture

See `docs/DESIGN.md` for full specification including state machine, checkpoint format, and subagent lifecycle.
