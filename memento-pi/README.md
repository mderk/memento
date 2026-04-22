# memento-pi

pi-coding-agent extension that embeds [memento-workflow](../memento-workflow) in-process — no MCP server.

## Status

MVP scaffold (shape-only). Step 3 of the porting plan:

- [x] Python JSONL stdio server (`memento-workflow/scripts/server.py`)
- [x] Extension scaffold, `/wf list`
- [ ] RPC client + server bootstrap (`session_start` / `session_shutdown`)
- [ ] `workflow_submit` tool + auto-run loop for `shell` / `ask_user` actions
- [ ] `before_agent_start` injection of pending action into the system prompt
- [ ] Widget + `/wf start|status|cancel|runs`

## Install (local dev)

```bash
pi install -l /Users/max/Documents/projects/memento/memento-pi
```

Requires `uv run python -m scripts.server` to be runnable from the memento-workflow directory.

## Configuration

Set `MEMENTO_WORKFLOW_DIR` env var to the memento-workflow checkout (default: `~/Documents/projects/memento/memento-workflow`).
