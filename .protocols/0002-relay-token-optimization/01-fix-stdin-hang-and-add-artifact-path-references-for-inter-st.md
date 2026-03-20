---
id: 01-fix-stdin-hang-and-add-artifact-path-references-for-inter-st
status: in-progress
estimate: 2h
---
# Fix stdin hang and add artifact path references for inter-step data

## Objective

<!-- objective -->
Fix the subprocess hang bug when stdin dotpath fails to resolve, and establish the "pass the path, not the content" pattern for inter-step data transfer.

Currently shell steps use `stdin="{{results.step.structured_output}}"` to pipe data between steps. This resolves the dotpath → serializes to JSON → pipes via subprocess stdin. When resolution fails, `stdin_data=None` causes subprocess to inherit MCP server's stdin → hang until timeout.

The data already exists on disk as artifact files. Steps should reference file paths instead of piping content.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Fix stdin_data=None hang in shell_exec.py

- [ ] When stdin_data is None, pass stdin=subprocess.DEVNULL instead of input=None
  In `_execute_shell()`, when `stdin_data is None`, the subprocess must not inherit parent stdin. Use `stdin=subprocess.DEVNULL` or `input=""` to prevent hang.

  ```python
  proc = subprocess.run(
      cmd_argv,
      ...
      input=stdin_data if stdin_data is not None else "",
  )
  ```

- [ ] Add test for stdin_data=None behavior
  Test that a shell step with unresolvable stdin dotpath fails gracefully (empty input) instead of hanging.
<!-- /task -->

<!-- task -->
### Add artifact_dir to StepResult for file-based references

- [ ] Expose artifact path in step results
  StepResult already has `exec_key` and the artifact path is computed via `exec_key_to_artifact_path()`. Add a convenience field or dotpath pattern so downstream steps can reference `results.step.artifact_dir` to get the file path.

  This enables: `args='--file {{results.plan.artifact_dir}}/result.json'` instead of `stdin='{{results.plan.structured_output}}'`.
<!-- /task -->

<!-- task -->
### Externalize large start() variables to files in engine

- [ ] Auto-externalize large variables in runner.py start()
  When `start()` receives variables, the engine checks each string value. If `len(value) > THRESHOLD` (e.g. 1000 chars) and `artifacts_dir` is available, write to `{artifacts_dir}/var_{key}.txt`, replace the variable value with empty string, and set `{key}_file` to the file path.

  ```python
  # In runner.py start(), after creating artifacts_dir:
  for key, value in list(variables.items()):
      if isinstance(value, str) and len(value) > THRESHOLD:
          path = artifacts_dir / f"var_{key}.txt"
          path.write_text(value, encoding="utf-8")
          variables[key] = ""
          variables[f"{key}_file"] = str(path)
  ```

  This doesn't prevent MCP transport cost (data already arrived in the request), but prevents the value from being inlined into every subsequent prompt via `{{variables.key}}` substitution. Skills pass variables as usual, no changes needed per-skill.

- [ ] Update substitute_with_files to check for `_file` suffix variables
  When a prompt template references `{{variables.prd_source}}` and the value is empty but `prd_source_file` exists, read from the file path. Or: the existing externalization in `substitute_with_files` already handles this via `context_files` — verify it works with the new pattern.

- [ ] Add tests for auto-externalization
  Test that large variables are written to files and small variables remain inline.
<!-- /task -->

<!-- task -->
### Migrate create-protocol render step from stdin to file reference

- [ ] Update render-protocol ShellStep to use --file instead of --stdin
  In `create-protocol/workflow.py`, change:
  ```python
  # Before:
  ShellStep(stdin="{{results.plan-protocol.structured_output}}", args='render-protocol --stdin ...')
  # After:
  ShellStep(args='render-protocol --file {{results.plan-protocol.artifact_dir}}/result.json ...')
  ```

- [ ] Update protocol_md.py to accept --file argument
  Add `--file <path>` option alongside existing `--stdin`. When --file is given, read JSON from file instead of stdin.

- [ ] Test that render-protocol works with file reference
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- stdin_data=None must never cause subprocess hang
- Existing workflows using stdin dotpath must continue to work (stdin is not removed, just fixed)
- artifact_dir reference must work for any step that has artifacts
<!-- /constraints -->

## Implementation Notes

The stdin fix is a one-liner but prevents a class of silent hangs. The artifact_dir pattern is the more important change — it establishes the convention that inter-step data flows through files, not through the engine's variable resolution chain.

Check all existing workflows for `stdin=` usage and evaluate if they can be migrated to file references.

## Verification

<!-- verification -->
```bash
cd memento-workflow && uv run pytest tests/ -x -q
cd memento-workflow && uv run ruff check scripts/
```
<!-- /verification -->

## Starting Points

<!-- starting_points -->
- memento-workflow/scripts/infra/shell_exec.py
- memento-workflow/scripts/engine/types.py
- memento/static/workflows/create-protocol/workflow.py
- memento/static/workflows/process-protocol/protocol_md.py
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] None expected
