# PRD: Dry-Run Preview Mode

## 1. Introduction

The workflow engine already accepts `start(dry_run=True)` and has partial infrastructure for dry-run execution — placeholder actions, auto-recording, synthetic structured output. However, the current implementation returns actions one at a time (requiring a full relay loop), doesn't produce a useful summary, and the documented behavior ("returns ALL actions as a flat list") is not implemented.

This feature completes the dry-run mode so that a single `start(dry_run=True)` call returns a hierarchical execution preview with summary statistics — no relay loop needed.

## 2. Goals

- Complete the dry-run collect-all loop in the runner so `start(dry_run=True)` returns the full execution plan in one response
- Return a hierarchical step tree (reflecting loops, retries, parallel, groups) plus summary statistics
- Handle conditional branches: show which branches would be taken based on current variables
- Handle dynamic blocks: loops over unresolved lists show the template once with a note about the list source
- No side effects: no checkpoint files, no shell execution, no artifacts written

## 3. User Stories

- As a developer, I want to preview what `/develop "add caching"` will do before running it, so I can estimate scope and catch misconfigured workflows
- As a workflow author, I want to verify that my conditions and branches resolve correctly for given variables, without executing the full workflow
- As a protocol creator, I want to dry-run `/process-protocol 0005` to see how many steps and what shape the execution will take

## 4. Functional Requirements

1. `start(workflow, variables, dry_run=True)` MUST return a single response (action type `"dry_run_complete"`) containing:
   - `tree`: hierarchical list of steps, each with `exec_key`, `type` (shell/llm/prompt/parallel/loop/retry/group/subworkflow/conditional), `name`, and nested `children` for container blocks
   - `summary`: `{ step_count, steps_by_type, parallel_lane_count, conditional_branches_evaluated, skipped_blocks }`
2. The collect-all loop MUST advance through all blocks internally, without emitting individual actions to the relay
3. Conditional blocks MUST show which branch was taken (or "skipped — condition false")
4. Parallel blocks MUST show template expanded once per lane (or template with item_var placeholder if list is unresolved)
5. Loop blocks with unresolved `loop_over` MUST show template once with a note: "iterates over {dotpath}"
6. SubWorkflow blocks MUST recursively expand the referenced workflow's blocks in the tree
7. No checkpoint files, meta.json, or artifacts MUST be written during dry-run
8. Existing `_build_dry_run_action` and `_auto_record_dry_run` infrastructure MUST be reused where possible
9. The response MUST include `protocol_version: 1` and `run_id` (ephemeral, not stored)

## 5. Non-Goals

- Interactive dry-run (step-by-step relay) — single response is sufficient
- Cost/time estimation — no historical data exists yet (future: workflow analytics)
- Diff between two dry-runs — out of scope
- Dashboard visualization of dry-run results — out of scope
- Modifying any existing skill files to add --dry-run flags — users just pass the flag to start()

## 6. Design Considerations

The response format should be compact enough to fit in a single MCP response without overwhelming the relay agent's context. The tree format mirrors exec_key hierarchy (e.g., `loop:implement[i=0]/write-tests` appears as nested children).

## 7. Technical Considerations

- The partial dry-run infrastructure (actions.py, state.py, parallel.py) already handles per-block auto-recording and synthetic structured output
- The main gap is in `runner.py`: after `start()` returns the first dry-run action, nobody calls the collect-all loop
- Conditions evaluated in dry-run may differ from runtime if they depend on `results.*` from prior steps — synthetic results use placeholder values
- SubWorkflow expansion requires loading the referenced workflow from the registry, which is already available in `state.registry`

## 8. Success Metrics

- `start(dry_run=True)` returns complete tree+summary in a single call for all existing workflows (develop, code-review, commit, create-protocol, process-protocol, merge-protocol)
- No checkpoint/artifact files created during dry-run
- Tree correctly reflects conditional branch evaluation for given variables
- All existing tests continue to pass

## 9. Open Questions

- Should dry-run expand RetryBlock contents (showing one iteration) or just show "retry: name (max N attempts)"?
- Should unresolved template variables in commands show as `{{...}}` or be replaced with `<unresolved>`?
