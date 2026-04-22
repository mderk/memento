# Overview

`memento-pi` embeds [memento-workflow](../../memento-workflow) directly inside [pi-coding-agent](https://github.com/badlogic/pi-mono), replacing the MCP transport with an in-process pi extension.

## Why

MCP roundtrips add non-trivial latency per workflow step (JSON-RPC (de)serialization, process boundary, stdin/stdout), and MCP servers are transport-only — they can't hook into the agent lifecycle (pending-action injection, session teardown, UI widgets, user dialogs). A pi extension gets all three for free and communicates with the Python engine over a simpler JSONL stdio protocol.

The bigger win: pi's `createAgentSession` / `runAgent` API lets us run LLM steps **in-process as isolated sub-agents**, using the same provider (`claude-agent-sdk-pi`, Claude Pro subscription). Workflows become autonomous background runners — the user's main chat stays clean, progress shows in a widget, only interactive `ask_user` steps and final results surface.

## Scope (v0 MVP)

- One active workflow run per pi session (stack for subworkflows/subagents is v2).
- `LLMStep` (inline and `isolation="subagent"`) → `runAgent()` with per-step model.
- `ShellStep` → handled by Python engine's own `_auto_advance` (no TS involvement).
- `PromptStep` (`ask_user`) → `ctx.ui.confirm/select/input`.
- `SubWorkflow` with relay → v2 (stack of active runs).
- `ParallelEachBlock` → v2 (sequential fallback possible).

## Not in scope

- MCP compatibility mode.
- Dashboard (`open_dashboard`) — replaced by pi widget.
- Concurrent parallel lanes (sequential is fine for v0 if ever needed).
- Resume-selector UI on startup (manual `/wf resume <id>`, also v2).

## Entry points

- User: `/wf list | start <name> | status | cancel` commands, plus optional `workflow_submit` tool (see decisions.md — may be removed in auto mode).
- Extension boots a long-lived `python -m scripts.server` subprocess; talks JSONL over stdin/stdout.
