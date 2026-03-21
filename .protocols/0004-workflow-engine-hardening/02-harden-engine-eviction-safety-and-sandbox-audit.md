---
id: 02-harden-engine-eviction-safety-and-sandbox-audit
status: done
estimate: 1h
---
# Harden engine: eviction safety and sandbox audit

## Objective

<!-- objective -->
Two isolated engine fixes:

- **Eviction safety**: `_evict_terminal_runs` (runner.py:150-163) removes completed runs without checking if a parent still references them via `child_run_ids`. Current guard `not s.child_run_ids` only checks if the run HAS children, not if it IS a referenced child.
- **Sandbox audit**: `_sandbox_prefix` (sandbox.py:77) silently returns `[]` when `MEMENTO_SANDBOX=off`. Should log a warning.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Add parent-reference check to _evict_terminal_runs

A child run can be terminal (completed) and have no children of its own, yet its parent still references it in `child_run_ids`. Evicting it causes a dangling reference.

- [ ] Build set of referenced child IDs before eviction
  Before the list comprehension at line 152, collect all referenced IDs:

  ```python
  referenced = set()
  for s in _runs.values():
      referenced.update(s.child_run_ids)

  to_remove = [
      rid for rid, s in _runs.items()
      if s.status in _TERMINAL_RUN_STATUSES
      and not s.child_run_ids
      and rid not in referenced
  ]
  ```

- [ ] Add test: child run referenced by parent is not evicted

- [ ] Add test: unreferenced terminal run IS evicted
<!-- /task -->

<!-- task -->
### Log warning when sandbox is disabled

- [ ] Add logger.warning in _sandbox_prefix with once-per-process guard
  At sandbox.py:77, before `return []`:

  ```python
  _sandbox_off_warned = False  # module-level

  def _sandbox_prefix(cwd: str) -> list[str]:
      global _sandbox_off_warned
      if not SANDBOX_ENABLED:
          if not _sandbox_off_warned:
              logger.warning("Sandbox disabled via MEMENTO_SANDBOX=off — shell commands run unrestricted")
              _sandbox_off_warned = True
          return []
  ```

- [ ] Add test verifying warning is logged once
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- Eviction must not remove runs referenced by any parent's child_run_ids
- Sandbox warning logged at most once per process
- No performance regression in _evict_terminal_runs (runs under lock)
- All existing tests pass
<!-- /constraints -->

## Implementation Notes

`_evict_terminal_runs` is called with `_runs_lock` held. The `_runs` dict is small (threshold ~100), so O(n*m) where m is max child_run_ids count is acceptable.

For sandbox: use module-level `_sandbox_off_warned` flag. Use `logger.warning()` and test with `caplog` fixture.

## Verification

<!-- verification -->
```bash
# timeout:120 uv run pytest memento-workflow/tests/ -q
# timeout:120 uv run pytest memento/tests/ -q
```
<!-- /verification -->

## Starting Points

<!-- starting_points -->
- memento-workflow/scripts/runner.py
- memento-workflow/scripts/infra/sandbox.py
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] None expected
