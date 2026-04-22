# Runtime notes

## pi extension API (essentials used)

- Extension entry: `default function (pi: ExtensionAPI) { ... }` in `src/index.ts`, wired via `package.json > pi.extensions`.
- Event hooks: `pi.on("session_start" | "session_shutdown" | "before_agent_start" | "tool_call" | ...)`.
- Tools: `pi.registerTool({ name, label, description, parameters (TypeBox schema), async execute(id, params, signal, onUpdate, ctx) })`.
- Commands: `pi.registerCommand(name, { description, getArgumentCompletions?, handler(args, ctx) })`.
- `ctx.ui.notify(text, "info"|"success"|"warning"|"error")` — toast.
- `ctx.ui.confirm(title, msg)` / `select(title, items)` / `input(title, msg, default)` — sync dialogs (return `null` if cancelled / no TTY).
- `ctx.ui.setStatus(id, text)` — footer line; empty = clear.
- `ctx.ui.setWidget(id, lines[])` — multi-line widget above editor; `[]` = clear.
- `ctx.signal` — AbortSignal for current turn; undefined outside turns (e.g. inside command handlers when idle).
- `ctx.modelRegistry.find(provider, id)` → model; `getApiKey(provider)` → string or null.
- `pi.getAllTools()` — list of {name, description, parameters, sourceInfo}.

## In-process sub-agent

```ts
import { createAgent, createAgentSession, runAgent, defaultStopCondition } from "@mariozechner/pi-coding-agent";

const tools = pi.getAllTools().filter(t => allowedNames.includes(t.name));
const session = createAgentSession({ tools });
const agent   = createAgent({ model, apiKey });
session.appendMessage({ role: "user", content: [{type:"text", text: userMessage}], timestamp: Date.now() });
const result = await runAgent({ agent, session, systemPrompt, signal, stopWhen: defaultStopCondition, onUpdate });
const last = session.getEntries().filter(e => e.type === "message").at(-1);  // typically assistant
const finalText = /* extract .content[].text */;
```

Reference implementation: `packages/coding-agent/examples/extensions/subagent/index.ts` in pi-mono.

## Python server

- Runs via `uv run python -m scripts.server` from `$MEMENTO_WORKFLOW_DIR` (default `~/Documents/projects/memento/memento-workflow`).
- Exports: `start`, `submit`, `next`, `cancel`, `status`, `list_workflows`, `cleanup_runs`, `open_dashboard`.
- `_coerce_result()` parses string JSON returned by `runner.py` into objects for clean client-side use.
- Logs to stderr; TS prefixes with `[memento-pi]`.

## Engine actions (what TS sees)

After `_auto_advance`, engine never emits `shell` to the outside. Externally visible:
- `ask_user` — handled inline by ctx.ui.
- `prompt` — inline LLM step. `prompt_file` may point to a cached template file; read it to get the full text.
- `subagent` — same as prompt but with isolation hint; fields `relay`, `child_run_id` distinguish nested workflows (v2).
- `parallel` — `lanes[]` each with `child_run_id` + prompt (v2).
- `completed` / `halted` / `error` / `cancelled` — terminal.
- `_shell_log` field on an action carries per-step shell stats for debug (off by default).

## Workflow discovery

`list_workflows` scans: engine-bundled `skills/`, project `cwd/.workflows/`, plus any `--workflow-dirs`. Returns `{name, description, blocks, source}[]`. Python-DSL workflows are loaded via `scripts/infra/loader.py` — classes `WorkflowDef`, `LLMStep`, etc. are injected into the module namespace at import time (hence the `TYPE_CHECKING` pattern in `.workflows/*/workflow.py`).

## Install (local dev)

```bash
pi install -l /Users/max/Documents/projects/memento/memento-pi   # adds absolute path to .pi/settings.json
# or edit .pi/settings.json directly to bypass the relative-path bug on symlinked dirs
```

`/reload` in pi picks up TS source changes without restart (jiti under the hood). `package.json` changes need full restart.

## Test harness

```bash
# raw JSONL probe of the python server:
cd $MEMENTO_WORKFLOW_DIR && echo '{"id":"1","method":"list_workflows","params":{"cwd":"."}}' | uv run python -m scripts.server

# exercise the extension non-interactively:
cd <project-with-.workflows> && pi --print "/wf list" --no-tools
```

## Environment

- `MEMENTO_WORKFLOW_DIR` — path to the memento-workflow checkout.
- `MEMENTO_DEFAULT_MODEL` — override default model for LLMSteps with no explicit `model`.
- `MEMENTO_SHELL_LOG=1` — include `_shell_log` in action payloads (bloats context, debug only).
- `MEMENTO_SANDBOX=off` — disable macOS Seatbelt / Linux bubblewrap in shell steps.
- `WORKFLOW_DEBUG=1` — verbose Python logs to stderr.
