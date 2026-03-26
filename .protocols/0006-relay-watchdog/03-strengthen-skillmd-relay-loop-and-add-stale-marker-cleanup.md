---
id: 03-strengthen-skillmd-relay-loop-and-add-stale-marker-cleanup
status: done
estimate: 1h
---
# Strengthen SKILL.md relay loop and add stale marker cleanup

## Objective

<!-- objective -->
Update the relay protocol documentation to prevent loop breaks (prevention), add watchdog documentation so the agent understands recovery, and add stale marker cleanup to `cleanup_runs()`.
<!-- /objective -->

## Tasks

<!-- tasks -->

<!-- task -->
### Update SKILL.md relay loop section

- [ ] Strengthen relay loop steps 5-6
  Change step 5 to: "**Immediately** go to step 2 — process the returned action right away."
  Change step 6 to: "Stop only when you receive `{"action": "completed"}`, `{"action": "halted"}`, or `{"action": "error"}`."

  Add after the loop steps:
  > **Never break the loop.** Each submit returns the next action — process it without stopping. Brief commentary between steps is fine, but always continue to the next action in the same turn.

- [ ] Add 'Never break the relay loop' to Key Rules
  Add bullet: "**Never break the relay loop**: After submit returns the next action, process it immediately. The relay watchdog will catch accidental breaks, but prevention is better."

- [ ] Add Relay Watchdog section
  Brief section after Key Rules explaining the watchdog mechanism — so the agent understands what's happening when the Stop hook fires and tells it to call `next(run_id)`.
<!-- /task -->

<!-- task -->
### Add stale marker cleanup to runner.py

- [ ] Add marker cleanup helper function
  Add `_cleanup_stale_relay_markers(cwd: str, max_age_hours: int = 24) -> int` to `runner.py`. Scans `.workflow-state/.active_relays/` for markers older than `max_age_hours`, removes them, returns count.

- [ ] Call cleanup from cleanup_runs()
  After existing cleanup logic in `cleanup_runs()`, call `_cleanup_stale_relay_markers()` and include the count in the result JSON.
<!-- /task -->

<!-- /tasks -->

## Constraints

<!-- constraints -->
- SKILL.md changes must not break backward compatibility for existing relay agents
- Stale marker cleanup must not interfere with active relay markers
- runner.py change is minimal — only the cleanup helper and its call site
<!-- /constraints -->

## Implementation Notes

The `cleanup_runs()` function at runner.py:1519 delegates to `scripts/infra/cleanup.py`. The stale marker cleanup can be added directly in `cleanup_runs()` after the main cleanup call, since it's a simple directory scan independent of the run cleanup logic.

`_cleanup_stale_relay_markers` reads each `.json` file in `.active_relays/`, parses `created_at`, removes if older than threshold. Corrupt files are also removed.

## Verification

<!-- verification -->
```bash
cd memento-workflow && uv run pytest -v
cd memento-workflow && uv run pytest tests/test_relay_protocol_docs.py -v
```
<!-- /verification -->

## Context

<!-- context:files -->
- memento-workflow/docs/DESIGN.md
<!-- /context:files -->

## Starting Points

<!-- starting_points -->
- memento-workflow/skills/workflow-engine/SKILL.md
- memento-workflow/scripts/runner.py
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] None expected
