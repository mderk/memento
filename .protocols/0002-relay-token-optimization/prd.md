# Relay Token Optimization — Requirements

## Problem Statement

The memento-workflow relay architecture passes all data through the LLM context window. Prompts (10-50KB), JSON schemas, and completed summaries are sent inline in MCP tool responses, consuming significant tokens. In parallel lanes, identical prompts and schemas are duplicated per lane, multiplying the cost.

Additionally, inter-step data transfer uses inline variable resolution (dotpath → dict → json.dumps → stdin pipe) instead of file path references, even when the data already exists on disk as an artifact. This adds unnecessary serialization overhead and causes a hang bug when stdin dotpath fails to resolve (subprocess inherits MCP server's stdin).

## Requirements

- Prompt actions must support file-based prompt delivery: server writes prompt to artifact file, action contains path instead of inline text
- CompletedAction must support compact mode: totals + failed/skipped steps only, omitting per-step entries for successful steps
- Prompt actions must support schema-by-reference: schemas written to files at compile time, action contains path instead of inline JSON schema
- All changes must be backward-compatible: inline mode remains the default, file-based mode is opt-in or auto-detected
- Relay protocol documentation must be updated to handle new action fields (prompt_file, schema_file, shared_prompt)
- Inter-step data transfer must use artifact file paths instead of inline variable piping: shell steps should reference `{artifact_dir}/result.json` instead of `stdin="{{results.step.structured_output}}"`
- Fix stdin_data=None hang bug: when stdin dotpath fails to resolve, subprocess must not inherit parent stdin
- Engine must auto-externalize large start() variables to artifact files at receive time: prevents repeated inline substitution in downstream prompts (does not eliminate MCP transport cost — relay has no pre-start write target)

## Constraints

- Cannot change MCP transport layer — optimization must happen at action serialization level
- LLM relay must still work with existing relay protocol (backward compatibility)
- File-based approach requires LLM to make Read tool calls, adding latency per prompt action
- Changes scoped to memento-workflow/scripts/ — no changes to Claude Code itself

## Acceptance Criteria

- Prompt action with prompt_file field: LLM reads prompt from file instead of receiving inline, verified by test workflow run with reduced MCP response size
- Completed action for 50+ step workflow: compact summary contains only totals and non-success steps, response size is constant regardless of success count
- Schema reference: repeated prompt actions with same schema — schema transmitted once, subsequent actions contain reference only
- Existing workflows (commit, test-workflow, process-protocol) continue to work without relay protocol changes
- Shell steps with stdin: when stdin_data resolves to None, subprocess gets empty stdin (not parent's stdin) — no hang
- create-protocol render step uses --file with artifact path instead of --stdin with piped data
- start() with large variable (e.g. prd_source): engine auto-externalizes to artifact file after receiving — variable not inlined in subsequent prompt substitutions

## Source

Generated from task description: 2026-03-20
