---
name: cleanup
description: Clean up old workflow state directories to free disk space
version: 1.0.0
---

# Workflow State Cleanup

Remove old `.workflow-state/` run directories to free disk space.

## Usage

Call `mcp__plugin_memento-workflow_memento-workflow__cleanup_runs` with:

- `cwd`: project directory (defaults to `.`)
- `before`: remove runs started before this date (ISO 8601 or `YYYY-MM-DD`)
- `status_filter`: only remove runs with this status (`completed`, `running`, `error`)
- `keep`: keep the N most recent matching runs (default: 0)
- `dry_run`: preview what would be deleted without deleting
- `remove_all`: remove ALL runs (ignores other filters)

## Examples

| Goal | Parameters |
|------|------------|
| Remove all completed runs older than a week | `before: "2026-03-07", status_filter: "completed"` |
| Remove everything, keep last 5 | `remove_all: true, keep: 5` |
| Preview cleanup | `remove_all: true, dry_run: true` |
| Remove orphaned/stuck runs | `status_filter: "running"` |

## CLI

```bash
cd memento-workflow
python -m scripts.cleanup --before 2026-03-01
python -m scripts.cleanup --status completed --keep 5
python -m scripts.cleanup --all --dry-run
```
