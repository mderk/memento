"""Clean up old workflow state directories.

Usage:
    python -m scripts.cleanup [OPTIONS] [CWD]

Options:
    --before DATE    Remove runs started before this date (ISO 8601 or YYYY-MM-DD)
    --status STATUS  Only remove runs with this status (completed, running, error)
    --keep N         Keep the N most recent runs (default: 0 = don't keep)
    --dry-run        Show what would be deleted without deleting
    --all            Remove ALL runs (ignores --before/--status filters)

Examples:
    python -m scripts.cleanup --before 2026-03-01
    python -m scripts.cleanup --status completed --keep 5
    python -m scripts.cleanup --all --dry-run
    python -m scripts.cleanup --before 2026-03-10 --status completed /path/to/project
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def _parse_date(date_str: str) -> datetime:
    """Parse date string (ISO 8601 or YYYY-MM-DD) into timezone-aware datetime."""
    date_str = date_str.strip()
    # YYYY-MM-DD → start of day UTC
    if len(date_str) == 10 and date_str[4] == "-" and date_str[7] == "-":
        return datetime.fromisoformat(date_str + "T00:00:00+00:00")
    dt = datetime.fromisoformat(date_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _load_meta(run_dir: Path) -> dict | None:
    """Load meta.json from a run directory, or None if missing/corrupt."""
    meta_path = run_dir / "meta.json"
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return None


def scan_runs(state_dir: Path) -> list[dict]:
    """Scan .workflow-state/ and return list of run info dicts."""
    runs = []
    if not state_dir.exists():
        return runs
    for entry in sorted(state_dir.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        meta = _load_meta(entry)
        runs.append(
            {
                "run_id": entry.name,
                "path": entry,
                "meta": meta,
                "status": meta.get("status", "unknown") if meta else "unknown",
                "started_at": meta.get("started_at", "") if meta else "",
                "workflow": meta.get("workflow", "") if meta else "",
            }
        )
    return runs


def filter_runs(
    runs: list[dict],
    *,
    before: datetime | None = None,
    status: str | None = None,
    keep: int = 0,
    remove_all: bool = False,
) -> list[dict]:
    """Filter runs to determine which should be removed."""
    if remove_all:
        candidates = list(runs)
    else:
        candidates = []
        for r in runs:
            match = True
            if before and r["started_at"]:
                try:
                    run_dt = _parse_date(r["started_at"])
                    if run_dt >= before:
                        match = False
                except (ValueError, TypeError):
                    pass  # can't parse date → include in candidates
            elif before and not r["started_at"]:
                pass  # no date → include (probably orphan)
            if status and r["status"] != status:
                match = False
            if match:
                candidates.append(r)

    if keep > 0:
        # Sort by started_at descending, keep the most recent N
        candidates.sort(
            key=lambda r: r["started_at"] or "",
            reverse=True,
        )
        candidates = candidates[keep:]

    return candidates


def cleanup(
    cwd: str = ".",
    *,
    before: str | None = None,
    status: str | None = None,
    keep: int = 0,
    dry_run: bool = False,
    remove_all: bool = False,
) -> dict:
    """Clean up workflow state directories.

    Returns summary dict with removed/skipped counts and details.
    """
    state_dir = Path(cwd).resolve() / ".workflow-state"
    if not state_dir.exists():
        return {
            "status": "success",
            "message": "No .workflow-state/ directory found",
            "removed": 0,
            "skipped": 0,
        }

    runs = scan_runs(state_dir)
    if not runs:
        return {
            "status": "success",
            "message": "No runs found",
            "removed": 0,
            "skipped": 0,
        }

    try:
        before_dt = _parse_date(before) if before else None
    except (ValueError, TypeError):
        return {
            "status": "error",
            "error": f"Invalid before date: {before}",
            "removed": 0,
            "skipped": 0,
        }

    to_remove = filter_runs(
        runs,
        before=before_dt,
        status=status,
        keep=keep,
        remove_all=remove_all,
    )
    remove_ids = {r["run_id"] for r in to_remove}

    removed = []
    skipped = []
    total_freed = 0

    for r in runs:
        if r["run_id"] in remove_ids:
            try:
                size = sum(
                    f.stat().st_size for f in r["path"].rglob("*") if f.is_file()
                )
            except OSError:
                size = 0
            if not dry_run:
                shutil.rmtree(r["path"], ignore_errors=True)
            removed.append(
                {
                    "run_id": r["run_id"],
                    "workflow": r["workflow"],
                    "status": r["status"],
                    "started_at": r["started_at"],
                    "size": size,
                }
            )
            total_freed += size
        else:
            skipped.append(
                {
                    "run_id": r["run_id"],
                    "workflow": r["workflow"],
                    "status": r["status"],
                    "started_at": r["started_at"],
                }
            )

    return {
        "status": "success",
        "dry_run": dry_run,
        "removed": len(removed),
        "skipped": len(skipped),
        "freed_bytes": total_freed,
        "freed_mb": round(total_freed / 1_048_576, 2),
        "details": removed,
    }


def cleanup_stale_relay_markers(cwd: str, max_age_hours: int = 24) -> int:
    """Remove relay watchdog markers older than max_age_hours. Returns count removed."""
    marker_dir = Path(cwd).resolve() / ".workflow-state" / ".active_relays"
    if not marker_dir.is_dir():
        return 0
    removed = 0
    now = datetime.now(timezone.utc)
    for f in marker_dir.iterdir():
        if not f.name.endswith(".json"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            created = datetime.fromisoformat(data["created_at"])
            age_hours = (now - created).total_seconds() / 3600
            if age_hours <= max_age_hours:
                continue
        except (json.JSONDecodeError, KeyError, OSError, TypeError, ValueError):
            pass  # corrupt or unreadable — remove
        try:
            f.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def main():
    parser = argparse.ArgumentParser(
        description="Clean up old workflow state directories",
    )
    parser.add_argument(
        "cwd",
        nargs="?",
        default=".",
        help="Project directory containing .workflow-state/",
    )
    parser.add_argument(
        "--before",
        default=None,
        help="Remove runs started before this date (ISO 8601 or YYYY-MM-DD)",
    )
    parser.add_argument(
        "--status",
        default=None,
        choices=["completed", "running", "error", "unknown"],
        help="Only remove runs with this status",
    )
    parser.add_argument(
        "--keep", type=int, default=0, help="Keep the N most recent matching runs"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without deleting",
    )
    parser.add_argument(
        "--all",
        dest="remove_all",
        action="store_true",
        help="Remove ALL runs (ignores --before/--status)",
    )
    args = parser.parse_args()

    if not args.before and not args.status and not args.remove_all:
        parser.error("Specify --before, --status, --all, or a combination")

    result = cleanup(
        args.cwd,
        before=args.before,
        status=args.status,
        keep=args.keep,
        dry_run=args.dry_run,
        remove_all=args.remove_all,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
