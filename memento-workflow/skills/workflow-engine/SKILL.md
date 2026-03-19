---
name: workflow-engine
description: Relay protocol for executing workflows via the memento-workflow MCP server. Load this skill before running any workflow.
version: 3.0.0
---

# Workflow Engine — Relay Protocol

You are a relay agent driving a workflow via the `memento-workflow` MCP server. The server manages all state, control flow, and shell execution internally. You only handle interactive actions.

## Relay Loop

1. Call `mcp__plugin_memento-workflow_memento-workflow__start(workflow, variables, cwd, workflow_dirs)` to begin. Returns first action.
2. **Show the `_display` field** from the action to the user as a brief status line (e.g., `Step [build]: Running shell — npm run build`). Every action includes `_display`.
3. Execute the action (see Action Handlers below).
4. Call `mcp__plugin_memento-workflow_memento-workflow__submit(run_id, exec_key, output, status)` with the result. Returns next action.
5. Repeat from step 2 until you receive `{"action": "completed"}`.
6. If you lose track, call `mcp__plugin_memento-workflow_memento-workflow__next(run_id)` to re-fetch the current pending action without mutating state.

## Action Handlers

### `ask_user` — Present question to the user

Use the `AskUserQuestion` tool to present the question to the user. Map the `prompt_type` field:

- `"choice"` — Present options. Set `multiSelect: false`. Map `options` to AskUserQuestion option labels. Use `message` as the question text.
- `"confirm"` — Yes/no question. Provide "Yes" and "No" as options.
- `"input"` — Open-ended question. Provide 2-3 reasonable suggestion options (inferred from context) so the user can pick one or type a custom answer.

**Submitting the answer — mechanical rule:**

```
submit(run_id=<from action>, exec_key=<from action>, output=<AskUserQuestion return value>, status="success")
```

- `output` = the EXACT string returned by AskUserQuestion. No modification.
- `status` = ALWAYS `"success"`. The server handles validation, retries, and cancellation. You are a pipe.

If the server returns `ask_user` again (with `retry: true`), present it the same way and submit the same way.

Correct examples:

- User picks "accept" → `submit(output="accept", status="success")`
- User types "?" → `submit(output="?", status="success")`
- User picks "Stop workflow" → `submit(output="Stop workflow", status="success")`

NEVER do this:

- User types "?" → `submit(output="accept")` — never interpret the answer
- User types "?" → `submit(status="cancelled")` — never decide for the user

### `prompt` — Process LLM prompt inline

The action contains the full prompt text in the `prompt` field. Process it directly in your current context — read the prompt, follow its instructions, do the work it describes (read files, analyze code, generate output, etc.).

**Context files:** If `context_files` is present, read each file (using the Read tool) before processing the prompt. These files contain data referenced in the prompt text — the prompt will indicate where externalized data should be read from.

If `json_schema` is present, structure your output as JSON matching the schema. The field `output_schema_name` provides the schema name.

If `tools` includes `"ask_user"`, the prompt will instruct you to "call ask_user" — implement this by calling `AskUserQuestion` with the message and options described in the prompt, then include the user's answer in your output. Other tools in the list are guidance for which tools are relevant.

**Submitting results:** If `result_dir` is present, write your structured JSON result to `{result_dir}/result.json` (using the Write tool), then call `submit` with just `status="success"` — no `output` or `structured_output` needed. The engine reads the result from the file. If `result_dir` is absent, submit your result as `output` (plain text or JSON string) and pass structured JSON as `structured_output`.

### `subagent` with `relay: false` — Single-task isolated agent

Launch the `Agent` tool with the `prompt` from the action. The agent completes one task and returns.

If `context_hint` is present, summarize relevant context from your conversation (guided by the hint) and prepend it as a `## Context` section to the agent's prompt.

If `model` is specified, pass it to the Agent tool.

Submit the agent's return value as `output`. If the agent fails, submit with `status="failure"`.

### `subagent` with `relay: true` — Multi-step isolated agent with sub-relay

Launch the `Agent` tool. The agent's prompt should include:

1. Context summary (guided by `context_hint`)
2. The `prompt` from the action
3. Sub-relay instructions:

```
You have access to the memento-workflow MCP server. Run a sub-relay loop:
1. Call mcp__plugin_memento-workflow_memento-workflow__next("{child_run_id}") to get the first action.
2. Execute each action based on its type:
   - "prompt" actions: process the prompt text inline. Read any files listed in "context_files" first. If "json_schema" is present, your output MUST be valid JSON matching that schema. If "result_dir" is present, write your JSON result to {result_dir}/result.json and submit with just status="success" (no output needed). If the action has "tools": ["ask_user"], the prompt will instruct you to "call ask_user" — implement this by calling AskUserQuestion with the message and options from the prompt, then include the user's answer in your output.
   - "ask_user" actions: present the question using AskUserQuestion.
3. Call mcp__plugin_memento-workflow_memento-workflow__submit("{child_run_id}", exec_key, output, status) after each.
4. Continue until you receive {"action": "completed"}.
5. Return a summary of what you accomplished.
```

Replace `{child_run_id}` with the actual `child_run_id` from the action.

After the agent returns, submit the agent's summary as `output` to the **parent** run_id with the **parent** exec_key.

**Fallback:** If the Agent tool refuses (stochastic injection defense), handle the sub-relay inline — call `next(child_run_id)`, process each action, `submit` results, until `completed`.

### `parallel` — Multiple simultaneous agents

Launch multiple `Agent` tools simultaneously — one per lane in the `lanes` array.

If `model` is present at the top level, pass it to each Agent tool launch.

Each lane has its own `child_run_id` and `prompt`. Each agent runs a sub-relay loop on its lane's `child_run_id` (same instructions as `subagent` with `relay: true`).

After all agents return, combine their summaries and submit to the parent `run_id` with the parent `exec_key`.

**Before launching agents:** Background agents cannot prompt the user for file permissions. Before launching, ensure write mode is active by creating the output directory via Bash: `mkdir -p <clean_dir>` (where `clean_dir` is from the workflow variables or the action context). This triggers the permission prompt if needed, so background agents inherit write access.

**Fallback:** If the Agent tool refuses (stochastic injection defense), handle the sub-relay inline — call `next(child_run_id)`, process each action, `submit` results, until `completed`.

### `completed` — Workflow finished

Report the workflow summary to the user. The `summary` field contains results.

### `halted` — Workflow stopped by halt directive

A step triggered a halt, stopping the entire workflow. Report `reason` and `halted_at` to the user. This is not an error — it's a deliberate stop (e.g., a step failed verification and continuing would be unsafe). The checkpoint is preserved for potential resume after the issue is fixed.

### `error` — Protocol error

Report the error to the user. Common causes:

- Wrong `exec_key`: the `expected_exec_key` field shows what was expected
- Unknown `run_id`: the run may have been cancelled or never started
- Workflow already completed

## MCP Tools Reference

| Tool             | Parameters                                                                                                                     | Description                                 |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------- |
| `start`          | `workflow`, `variables={}`, `cwd=""`, `workflow_dirs=[]`, `resume=""`, `dry_run=false`, `shell_log=false`                       | Start or resume a workflow                  |
| `submit`         | `run_id`, `exec_key`, `output=""`, `structured_output=null`, `status="success"`, `error=null`, `duration=0.0`, `cost_usd=null`, `shell_log=false` | Submit result, get next action (idempotent) |
| `next`           | `run_id`, `shell_log=false`                                                                                                    | Re-fetch pending action (read-only)         |
| `cancel`         | `run_id`                                                                                                                       | Cancel workflow, clean up state             |
| `list_workflows` | `cwd=""`, `workflow_dirs=[]`                                                                                                   | List available workflows                    |
| `status`         | `run_id`                                                                                                                       | Get workflow state for debugging            |

## Key Rules

- **Shell steps are invisible**: The MCP server executes them internally via `subprocess.run()`. You never see `shell` actions. Pass `shell_log=true` to `start`/`submit`/`next` to include `_shell_log` in responses (off by default to save tokens).
- **Control flow is invisible**: Loops, retries, conditionals, subworkflows are resolved inside the state machine. You just process one action at a time.
- **`exec_key` is sacred**: Always submit the exact `exec_key` from the action you're responding to.
- **Idempotent submits**: Submitting the same `(run_id, exec_key)` twice is safe — returns the same next action.
- **One action at a time**: Each run has exactly one pending action. Process it, submit, get the next.
