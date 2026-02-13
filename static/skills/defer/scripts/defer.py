#!/usr/bin/env python3
"""
Deterministic operations for the deferred work backlog.

Usage:
    python defer.py bootstrap
    python defer.py create --title "..." --type debt --priority p2 --origin "..."
    python defer.py close <slug>
    python defer.py list [--status open]
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

VALID_TYPES = ("bug", "debt", "idea", "risk")
VALID_PRIORITIES = ("p0", "p1", "p2", "p3")
VALID_STATUSES = ("open", "scheduled", "closed")

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
"""

TEMPLATE_CONTENT = """\
---
title: ""
type: ""        # bug | debt | idea | risk
priority: ""    # p0 (critical) | p1 (high) | p2 (medium) | p3 (low)
status: open    # open | scheduled | closed
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

    bootstrapped = ensure_backlog()

    slug = unique_slug(slugify(args.title))
    item_path = ITEMS_DIR / f"{slug}.md"

    title_yaml = yaml_escape(args.title)
    origin_yaml = yaml_escape(args.origin or "")

    content = f"""\
---
title: {title_yaml}
type: {args.type}
priority: {args.priority}
status: open
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


def cmd_list(args):
    """List backlog items with optional status filter."""
    if not ITEMS_DIR.exists():
        output({"action": "list", "count": 0, "items": []})
        return

    items = []
    for f in sorted(ITEMS_DIR.glob("*.md")):
        text = f.read_text()
        meta = {}
        if text.startswith("---"):
            end = text.find("---", 3)
            if end != -1:
                for line in text[3:end].strip().splitlines():
                    if ":" in line:
                        key, val = line.split(":", 1)
                        meta[key.strip()] = val.strip().strip('"')

        if args.status and meta.get("status") != args.status:
            continue

        items.append({
            "slug": f.stem,
            "title": meta.get("title", ""),
            "type": meta.get("type", ""),
            "priority": meta.get("priority", ""),
            "status": meta.get("status", ""),
            "origin": meta.get("origin", ""),
        })

    output({
        "action": "list",
        "count": len(items),
        "items": items,
    })


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
    create_p.add_argument("--origin", default="")
    create_p.add_argument("--description", default="")

    close_p = sub.add_parser("close", help="Close and archive a backlog item")
    close_p.add_argument("slug")

    list_p = sub.add_parser("list", help="List backlog items")
    list_p.add_argument("--status", choices=VALID_STATUSES, default=None)

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
        "link-finding": cmd_link_finding,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
