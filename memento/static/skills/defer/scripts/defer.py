#!/usr/bin/env python3
"""
Deterministic operations for the deferred work backlog.

Usage:
    python defer.py bootstrap
    python defer.py create --title "..." --type debt --priority p2 --origin "..." [--area batch] [--effort m]
    python defer.py close <slug>
    python defer.py list [--status open] [--type bug] [--area batch] [--priority p1]
    python defer.py view --group-by priority [-o .backlog/views/by-priority.md] [--type bug] [--area batch]
    python defer.py link-finding <step-file> <slug> <title>

All output is JSON for easy parsing by Claude.
"""

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

BACKLOG_DIR = Path(".backlog")
ITEMS_DIR = BACKLOG_DIR / "items"
ARCHIVE_DIR = BACKLOG_DIR / "archive"
TEMPLATES_DIR = BACKLOG_DIR / "templates"

VIEWS_DIR = BACKLOG_DIR / "views"

VALID_TYPES = ("bug", "debt", "idea", "risk")
VALID_PRIORITIES = ("p0", "p1", "p2", "p3")
VALID_EFFORTS = ("xs", "s", "m", "l", "xl")
VALID_STATUSES = ("open", "scheduled", "closed")
VALID_GROUP_BY = ("priority", "type", "area", "effort", "status")

README_CONTENT = """\
# Backlog

Structured pool for deferred work — bugs, tech debt, ideas, and risks that are valuable but out of scope for the current task.

## When to add items

- **Bug** found outside current change scope
- **Tech debt** uncovered (tight coupling, missing tests, risky abstractions)
- **Idea** for improvement not part of the current objective
- **Risk** identified (security hardening, performance footgun, missing monitoring)

Do NOT defer items that affect the current task outcome — those become protocol tasks.

## How to add items

Run `/defer`. Or copy `templates/item.md` to `items/<short-slug>.md` manually.

## Lifecycle

open → scheduled → closed

- **open** — captured, not yet planned
- **scheduled** — assigned to a protocol or sprint
- **closed** — resolved; move file from `items/` to `archive/`

## Conventions

- File naming: `<short-slug>.md` — lowercase, hyphens
- One item per file for stable linking
- Always record origin (protocol step, code review)
- AI agents: load only `items/`, not `archive/`, to minimize context
- Triage when active items exceed ~30

## Views

Auto-generated dashboards live in `views/`. Regenerate with:

```bash
python defer.py view --group-by priority -o .backlog/views/by-priority.md
python defer.py view --group-by area -o .backlog/views/by-area.md
python defer.py view --group-by type -o .backlog/views/by-type.md
```
"""

TEMPLATE_CONTENT = """\
---
title: ""
type: ""        # bug | debt | idea | risk
priority: ""    # p0 (critical) | p1 (high) | p2 (medium) | p3 (low)
status: open    # open | scheduled | closed
area: ""        # freeform domain tag, e.g. batch, map, bot, auth
effort: ""      # xs | s | m | l | xl — fill during triage
origin: ""      # e.g. "protocol/step-03", "code-review", "development"
created: ""
---

## Description

<!-- What was discovered and why it matters -->

## Context

<!-- Where it was found, relevant code/files, links to protocol step or review -->

## Resolution criteria

<!-- What "done" looks like — optional, fill when scheduling -->
"""


def slugify(title: str) -> str:
    """Convert title to a filesystem-safe slug."""
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    slug = slug[:60]
    if not slug:
        # Non-ASCII or empty title: use hash-based fallback
        import hashlib
        slug = "item-" + hashlib.sha1(title.encode()).hexdigest()[:8]
    return slug


def unique_slug(base_slug: str) -> str:
    """Return a unique slug, appending -N suffix if needed."""
    candidate = base_slug
    counter = 2
    while (ITEMS_DIR / f"{candidate}.md").exists() or (ARCHIVE_DIR / f"{candidate}.md").exists():
        candidate = f"{base_slug}-{counter}"
        counter += 1
    return candidate


def yaml_escape(value: str) -> str:
    """Escape a string for safe YAML scalar output."""
    if not value:
        return '""'
    needs_quoting = (
        re.search(r'[:\#{}\[\],&*?|>!%@`"\'\\]', value)
        or value.startswith("-")
        or "\n" in value
    )
    if needs_quoting:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
    return value


def output(data: dict):
    """Print JSON result."""
    print(json.dumps(data, indent=2, ensure_ascii=False))


def error(msg: str):
    """Print JSON error and exit with code 1."""
    print(json.dumps({"error": msg}, ensure_ascii=False), file=sys.stderr)
    sys.exit(1)


def ensure_backlog() -> list[str]:
    """Create .backlog/ scaffolding if missing. Returns list of created paths."""
    created = []

    for d in [BACKLOG_DIR, ITEMS_DIR, ARCHIVE_DIR, TEMPLATES_DIR]:
        if not d.exists():
            d.mkdir(parents=True)
            created.append(str(d))

    readme = BACKLOG_DIR / "README.md"
    if not readme.exists():
        readme.write_text(README_CONTENT)
        created.append(str(readme))

    template = TEMPLATES_DIR / "item.md"
    if not template.exists():
        template.write_text(TEMPLATE_CONTENT)
        created.append(str(template))

    return created


# --- Commands ---

def cmd_bootstrap(_args):
    """Create .backlog/ scaffolding if it doesn't exist."""
    created = ensure_backlog()
    output({
        "action": "bootstrap",
        "already_existed": len(created) == 0,
        "created": created,
    })


def cmd_create(args):
    """Create a new backlog item."""
    if args.type not in VALID_TYPES:
        error(f"Invalid type '{args.type}'. Must be one of: {', '.join(VALID_TYPES)}")
    if args.priority not in VALID_PRIORITIES:
        error(f"Invalid priority '{args.priority}'. Must be one of: {', '.join(VALID_PRIORITIES)}")
    if args.effort and args.effort not in VALID_EFFORTS:
        error(f"Invalid effort '{args.effort}'. Must be one of: {', '.join(VALID_EFFORTS)}")

    bootstrapped = ensure_backlog()

    slug = unique_slug(slugify(args.title))
    item_path = ITEMS_DIR / f"{slug}.md"

    title_yaml = yaml_escape(args.title)
    origin_yaml = yaml_escape(args.origin or "")
    area_yaml = yaml_escape(args.area or "")
    effort = args.effort or ""

    content = f"""\
---
title: {title_yaml}
type: {args.type}
priority: {args.priority}
status: open
area: {area_yaml}
effort: {effort}
origin: {origin_yaml}
created: {date.today().isoformat()}
---

## Description

{args.description or '<!-- What was discovered and why it matters -->'}

## Context

<!-- Where it was found, relevant code/files, links to protocol step or review -->

## Resolution criteria

<!-- What "done" looks like — optional, fill when scheduling -->
"""
    item_path.write_text(content)

    result = {
        "action": "create",
        "slug": slug,
        "path": str(item_path),
        "title": args.title,
        "type": args.type,
        "priority": args.priority,
        "area": args.area or "",
        "effort": effort,
        "origin": args.origin or "",
    }
    if bootstrapped:
        result["bootstrapped"] = bootstrapped
    output(result)


def cmd_close(args):
    """Move item from items/ to archive/."""
    slug = args.slug.replace(".md", "")
    source = ITEMS_DIR / f"{slug}.md"

    if not source.exists():
        error(f"Item not found: {source}")

    if not ARCHIVE_DIR.exists():
        ARCHIVE_DIR.mkdir(parents=True)

    text = source.read_text()
    text = re.sub(r"^status:\s*\w+", "status: closed", text, count=1, flags=re.MULTILINE)
    target = ARCHIVE_DIR / f"{slug}.md"
    target.write_text(text)
    source.unlink()

    output({
        "action": "close",
        "slug": slug,
        "moved_from": str(source),
        "moved_to": str(target),
    })


def parse_frontmatter(text: str) -> dict:
    """Extract YAML frontmatter from markdown text."""
    meta = {}
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            for line in text[3:end].strip().splitlines():
                if ":" in line:
                    key, val = line.split(":", 1)
                    val = val.strip().strip('"')
                    # Strip inline comments
                    if "  #" in val:
                        val = val[:val.index("  #")].strip()
                    meta[key.strip()] = val
    return meta


def load_items() -> list[dict]:
    """Load all items from items/ directory."""
    if not ITEMS_DIR.exists():
        return []
    items = []
    for f in sorted(ITEMS_DIR.glob("*.md")):
        meta = parse_frontmatter(f.read_text())
        meta["slug"] = f.stem
        items.append(meta)
    return items


def filter_items(items: list[dict], *, status=None, type_=None, area=None,
                 priority=None, effort=None) -> list[dict]:
    """Filter items by any combination of fields."""
    result = items
    if status:
        result = [i for i in result if i.get("status") == status]
    if type_:
        result = [i for i in result if i.get("type") == type_]
    if area:
        result = [i for i in result if i.get("area") == area]
    if priority:
        result = [i for i in result if i.get("priority") == priority]
    if effort:
        result = [i for i in result if i.get("effort") == effort]
    return result


def cmd_list(args):
    """List backlog items with optional filters."""
    items = load_items()
    items = filter_items(
        items,
        status=args.status,
        type_=args.type,
        area=args.area,
        priority=args.priority,
        effort=args.effort,
    )

    out_items = []
    for meta in items:
        out_items.append({
            "slug": meta.get("slug", ""),
            "title": meta.get("title", ""),
            "type": meta.get("type", ""),
            "priority": meta.get("priority", ""),
            "status": meta.get("status", ""),
            "area": meta.get("area", ""),
            "effort": meta.get("effort", ""),
            "origin": meta.get("origin", ""),
        })

    output({
        "action": "list",
        "count": len(out_items),
        "items": out_items,
    })


def cmd_view(args):
    """Generate a markdown dashboard grouped by a field."""
    group_by = args.group_by
    if group_by not in VALID_GROUP_BY:
        error(f"Invalid group-by '{group_by}'. Must be one of: {', '.join(VALID_GROUP_BY)}")

    items = load_items()
    items = filter_items(
        items,
        status=args.status,
        type_=args.type,
        area=args.area,
        priority=args.priority,
        effort=args.effort,
    )

    # Group items
    groups: dict[str, list[dict]] = {}
    for item in items:
        key = item.get(group_by, "") or "(none)"
        groups.setdefault(key, []).append(item)

    # Sort groups: priorities/efforts have natural order, rest alphabetical
    if group_by == "priority":
        sort_order = list(VALID_PRIORITIES) + ["(none)"]
        sorted_keys = sorted(groups.keys(), key=lambda k: sort_order.index(k) if k in sort_order else 99)
    elif group_by == "effort":
        sort_order = list(VALID_EFFORTS) + ["(none)"]
        sorted_keys = sorted(groups.keys(), key=lambda k: sort_order.index(k) if k in sort_order else 99)
    else:
        sorted_keys = sorted(groups.keys())

    # Columns to show (exclude the group-by field itself)
    all_cols = ["priority", "type", "area", "effort", "origin"]
    cols = [c for c in all_cols if c != group_by]

    # Build filter description for header
    filters = []
    if args.status:
        filters.append(f"status={args.status}")
    if args.type:
        filters.append(f"type={args.type}")
    if args.area:
        filters.append(f"area={args.area}")
    if args.priority:
        filters.append(f"priority={args.priority}")
    if args.effort:
        filters.append(f"effort={args.effort}")
    filter_desc = f" ({', '.join(filters)})" if filters else ""

    # Build regeneration command
    cmd_parts = ["python .claude/skills/defer/scripts/defer.py view"]
    cmd_parts.append(f"--group-by {group_by}")
    if args.status:
        cmd_parts.append(f"--status {args.status}")
    if args.type:
        cmd_parts.append(f"--type {args.type}")
    if args.area:
        cmd_parts.append(f"--area {args.area}")
    if args.priority:
        cmd_parts.append(f"--priority {args.priority}")
    if args.effort:
        cmd_parts.append(f"--effort {args.effort}")
    if args.output:
        cmd_parts.append(f"-o {args.output}")
    regen_cmd = " ".join(cmd_parts)

    # Render markdown
    lines = []
    lines.append(f"# Backlog: by {group_by}{filter_desc}")
    lines.append("")
    lines.append(f"> Auto-generated. Regenerate: `{regen_cmd}`")
    lines.append(f"> {len(items)} items total")
    lines.append("")

    for key in sorted_keys:
        group_items = groups[key]
        lines.append(f"## {key} ({len(group_items)})")
        lines.append("")

        # Table header
        header = "| # | Title | " + " | ".join(c.capitalize() for c in cols) + " |"
        sep = "|---|-------|" + "|".join("---" for _ in cols) + "|"
        lines.append(header)
        lines.append(sep)

        for i, item in enumerate(group_items, 1):
            title = item.get("title", "")
            slug = item.get("slug", "")
            title_link = f"[{title}](../items/{slug}.md)"
            row_vals = [item.get(c, "") or "-" for c in cols]
            row = f"| {i} | {title_link} | " + " | ".join(row_vals) + " |"
            lines.append(row)

        lines.append("")

    md = "\n".join(lines)

    # Output to file or stdout
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md)
        output({
            "action": "view",
            "group_by": group_by,
            "items": len(items),
            "groups": len(groups),
            "output": str(out_path),
        })
    else:
        # Print markdown directly, then JSON summary to stderr
        print(md)


def find_repo_root(start: Path) -> Path:
    """Walk up from start to find the repo root (containing .git or .backlog)."""
    current = start.resolve()
    while current != current.parent:
        if (current / ".git").exists() or (current / ".backlog").exists():
            return current
        current = current.parent
    return Path.cwd().resolve()


def cmd_link_finding(args):
    """Insert a [DEFER] line into a step file's ## Findings section."""
    step_file = Path(args.step_file).resolve()
    if not step_file.exists():
        error(f"Step file not found: {step_file}")

    slug = args.slug.replace(".md", "")
    repo_root = find_repo_root(step_file)
    backlog_path = (repo_root / ITEMS_DIR / f"{slug}.md").resolve()

    # Compute relative path from step file's directory to the backlog item
    rel_path = os.path.relpath(backlog_path, step_file.parent).replace(os.sep, "/")
    defer_line = f"-   [DEFER] {args.title} → [{rel_path}]({rel_path})"

    text = step_file.read_text()

    findings_match = re.search(r"^## Findings\s*$", text, re.MULTILINE)
    if findings_match:
        insert_pos = findings_match.end()
        while insert_pos < len(text) and text[insert_pos] in ("\n", "\r"):
            insert_pos += 1
        text = text[:insert_pos] + "\n" + defer_line + "\n" + text[insert_pos:]
    else:
        text = text.rstrip() + "\n\n## Findings\n\n" + defer_line + "\n"

    step_file.write_text(text)

    output({
        "action": "link_finding",
        "step_file": str(args.step_file),
        "slug": slug,
        "relative_path": rel_path,
        "line_added": defer_line,
    })


def main():
    parser = argparse.ArgumentParser(description="Backlog management for deferred work")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("bootstrap", help="Create .backlog/ scaffolding")

    create_p = sub.add_parser("create", help="Create a new backlog item")
    create_p.add_argument("--title", required=True)
    create_p.add_argument("--type", required=True, choices=VALID_TYPES)
    create_p.add_argument("--priority", required=True, choices=VALID_PRIORITIES)
    create_p.add_argument("--area", default="")
    create_p.add_argument("--effort", default="")
    create_p.add_argument("--origin", default="")
    create_p.add_argument("--description", default="")

    close_p = sub.add_parser("close", help="Close and archive a backlog item")
    close_p.add_argument("slug")

    list_p = sub.add_parser("list", help="List backlog items")
    list_p.add_argument("--status", choices=VALID_STATUSES, default=None)
    list_p.add_argument("--type", default=None)
    list_p.add_argument("--area", default=None)
    list_p.add_argument("--priority", default=None)
    list_p.add_argument("--effort", default=None)

    view_p = sub.add_parser("view", help="Generate a markdown dashboard")
    view_p.add_argument("--group-by", required=True, choices=VALID_GROUP_BY)
    view_p.add_argument("-o", "--output", default=None, help="Output file path")
    view_p.add_argument("--status", default=None)
    view_p.add_argument("--type", default=None)
    view_p.add_argument("--area", default=None)
    view_p.add_argument("--priority", default=None)
    view_p.add_argument("--effort", default=None)

    link_p = sub.add_parser("link-finding", help="Add [DEFER] to a step file's Findings")
    link_p.add_argument("step_file")
    link_p.add_argument("slug")
    link_p.add_argument("title")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "bootstrap": cmd_bootstrap,
        "create": cmd_create,
        "close": cmd_close,
        "list": cmd_list,
        "view": cmd_view,
        "link-finding": cmd_link_finding,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
