---
id: 04-compact-completed-summary
status: done
estimate: 45m
---
# Compact completed summary

## Objective

<!-- objective -->
Add compact mode to `CompletedAction` so large workflows don't produce massive summaries. In compact mode, only totals and non-success steps are included. Success steps contribute to count only.

This makes summary size O(failures) instead of O(total_steps).
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Implement compact summary mode in _build_completed_action

- [ ] Add compact threshold logic
  When `len(state.ctx.results) > COMPACT_THRESHOLD` (e.g. 30), switch to compact mode automatically. In compact mode:

  ```python
  summary = {
      # Only non-success steps get individual entries
      key: entry for key, entry in full_summary.items()
      if entry["status"] != "success"
  }
  ```

  Totals already contain `step_count` and `steps_by_type` — that's sufficient for success tracking.

- [ ] Add `compact: bool` field to CompletedAction
  Optional field (default None, omitted from wire). Set to True when compact mode is active so relay knows the summary is filtered.
<!-- /task -->

<!-- task -->
### Add tests for compact summary

- [ ] Test compact mode triggers above threshold

- [ ] Test compact mode omits success entries

- [ ] Test below-threshold workflows get full summary
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- Compact mode must be auto-detected (no config needed)
- Totals must always be complete regardless of mode
- Non-success steps (failure, skipped) must always appear in summary
<!-- /constraints -->

## Implementation Notes

The `_build_completed_action` function in actions.py already iterates over `state.ctx.results`. The change is a filter: skip success entries when above threshold. The `compute_totals()` function in utils.py already computes aggregates from `results_scoped` independently.

## Verification

<!-- verification -->
```bash
cd memento-workflow && uv run pytest tests/ -x -q
```
<!-- /verification -->

## Starting Points

<!-- starting_points -->
- memento-workflow/scripts/engine/actions.py
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] None expected
