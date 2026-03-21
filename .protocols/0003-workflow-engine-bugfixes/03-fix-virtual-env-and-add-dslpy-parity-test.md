---
id: 03-engine-fixes
status: done
estimate: 2h
---
# Engine fixes: stdin, checkpoint, VIRTUAL_ENV, _dsl.py parity

## Objective

<!-- objective -->
Fix four engine-level bugs and add a parity test:

- **J. stdin not substituted**: `actions.py:57` passes `step.stdin` raw without stripping `{{}}` wrapper — `runner.py:316` resolves via `get_var()` expecting a bare dotpath, gets None → empty stdin. Discovered during create-protocol: render step received empty stdin.
- **K. _inline_parent_exec_key not persisted**: field set on inline SubWorkflow children but not saved/restored in checkpoints — breaks cascade completion on resume.
- **F**: Shell steps in worktrees see the main tree's VIRTUAL_ENV, causing pyright warnings
- **G**: No check that `_dsl.py` stub matches `types.py` block definitions
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Fix stdin template resolution in actions.py

`_build_shell_action()` passes `step.stdin` directly to `ShellAction.stdin` without any processing (line 57). But `runner.py:316` treats `action.stdin` as a dotpath and resolves via `state.ctx.get_var()`. When the workflow uses template syntax `{{results.foo.structured_output}}`, the `{{}}` wrapper causes `get_var()` to fail → returns None → subprocess gets empty stdin.

- [ ] Strip `{{}}` wrapper from step.stdin in actions.py
  In `_build_shell_action()`, resolve the template to a bare dotpath:

  ```python
  # Before:
  stdin=step.stdin or None,

  # After:
  stdin_val = step.stdin.strip() if step.stdin else None
  if stdin_val and stdin_val.startswith("{{") and stdin_val.endswith("}}"):
      stdin_val = stdin_val[2:-2].strip()
  ...
  stdin=stdin_val or None,
  ```

- [ ] Add test: ShellStep with stdin template resolves correctly
<!-- /task -->

<!-- task -->
### Fix VIRTUAL_ENV override in shell_exec.py

When shell steps run with a cwd that has its own `.venv/`, VIRTUAL_ENV should point there instead of the inherited parent environment's venv.

- [ ] Detect and override VIRTUAL_ENV based on cwd
  After building `merged_env` in `_execute_shell()`, add venv detection:

  ```python
  venv_in_cwd = Path(cwd) / ".venv"
  if venv_in_cwd.is_dir():
      merged_env["VIRTUAL_ENV"] = str(venv_in_cwd)
      merged_env["PATH"] = f"{venv_in_cwd}/bin:{merged_env.get('PATH', '')}"
  elif "VIRTUAL_ENV" in merged_env:
      venv_parent = Path(merged_env["VIRTUAL_ENV"]).parent
      if not Path(cwd).is_relative_to(venv_parent):
          del merged_env["VIRTUAL_ENV"]
  ```

  Logic:
  1. If cwd has `.venv/` → use it (worktree with own venv)
  2. Elif inherited VIRTUAL_ENV doesn't belong to cwd's tree → remove it
  3. Otherwise keep inherited VIRTUAL_ENV (normal case)

- [ ] Add test for VIRTUAL_ENV override behavior
<!-- /task -->

<!-- task -->
### Persist _inline_parent_exec_key in checkpoints

`RunState._inline_parent_exec_key` is set when an inline SubWorkflow child is created (subworkflow.py:145,189) but is NOT persisted in `checkpoint.py`. On resume, this field is empty → cascade completion of inline SubWorkflows breaks (runner.py:442-445 checks this field to cascade to parent).

- [ ] Save `_inline_parent_exec_key` in checkpoint_save
  In `checkpoint.py` `checkpoint_save()`, include `_inline_parent_exec_key` in the serialized state dict.

- [ ] Restore `_inline_parent_exec_key` in checkpoint_load
  In `checkpoint_load()` / `_restore_run_state()`, read and set the field on the restored RunState.

- [ ] Add test: resume inline SubWorkflow child preserves _inline_parent_exec_key
<!-- /task -->

<!-- task -->
### Add _dsl.py stub parity test

Create a test that extracts block type class names and their fields from `types.py` and verifies corresponding stubs exist in `_dsl.py`.

- [ ] Create test_dsl_parity.py
  Parse both files (AST or regex) and verify:
  1. Every Block subclass in `types.py` has a corresponding class in `_dsl.py`
  2. Each stub class has all the fields from the real class
  3. Field types are compatible

  Use `ast` module for reliable parsing.
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- stdin fix must handle both template syntax `{{path}}` and bare dotpath `path`
- VIRTUAL_ENV fix must not break shell steps running in the main project directory
- VIRTUAL_ENV fix must handle case where no .venv exists in cwd
- _dsl.py parity test must fail when a new field is added to types.py but not _dsl.py
- All existing tests pass
<!-- /constraints -->

## Implementation Notes

The `_dsl.py` stub exists in two places:
- `memento/static/workflows/_dsl.py` (source of truth — deployed to projects)
- `.workflows/_dsl.py` (local copy)

Both should be checked, but the test should primarily validate against `memento/static/workflows/_dsl.py`.

For VIRTUAL_ENV: `Path.is_relative_to()` requires Python 3.9+, which is fine for this project.

## Verification

<!-- verification -->
```bash
# timeout:120 cd memento-workflow && uv run pytest
# timeout:120 uv run pytest
```
<!-- /verification -->

## Starting Points

<!-- starting_points -->
- memento-workflow/scripts/engine/actions.py
- memento-workflow/scripts/runner.py
- memento-workflow/scripts/infra/checkpoint.py
- memento-workflow/scripts/infra/shell_exec.py
- memento-workflow/scripts/engine/types.py
- memento/static/workflows/_dsl.py
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] None expected
