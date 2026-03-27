# ruff: noqa: E501, T201
"""Protocol markdown primitives and renderer.

Shared module for parsing and generating protocol step files with
frontmatter + HTML marker format. No external dependencies.

## Markdown format

Step files use YAML-like flat frontmatter and HTML comment markers:

    ---
    id: 01-setup
    status: pending
    estimate: 2h
    ---
    # Step Name

    ## Objective
    <!-- objective -->
    ...
    <!-- /objective -->

    ## Tasks
    <!-- tasks -->
    <!-- task -->
    ### Heading
    - [ ] Item
    <!-- accept -->
    - Criterion 1
    <!-- /accept -->
    <!-- /task -->
    <!-- /tasks -->

## Renderer input schema (plain dicts)

    TaskItem  = {"title": str, "body"?: str, "subtasks"?: [TaskItem]}
    Task      = {"heading": str, "description"?: str, "subtasks"?: [TaskItem],
                 "acceptance_criteria"?: [str]}
    StepDef   = {"name": str, "objective": str, "tasks": [Task],
                 "constraints": [str], "impl_notes"?: str,
                 "verification": [str], "context_inline"?: str,
                 "context_files"?: [str], "starting_points"?: [str],
                 "memory_bank_impact"?: [str], "estimate": str}
    GroupDef  = {"title": str, "steps": [StepDef]}
    Protocol  = {"name": str, "context": str, "decision": str,
                 "rationale": str, "consequences_positive": [str],
                 "consequences_negative": [str], "items": [StepDef|GroupDef]}

An item is a GroupDef if it has a "steps" key, otherwise StepDef.
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------


def read_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    """Parse key: value frontmatter. Returns (metadata_dict, body_without_frontmatter)."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    try:
        end = text.index("\n---\n", 4)
    except ValueError:
        return {}, text
    fm_text = text[4:end]
    body = text[end + 5:]
    meta: dict[str, str] = {}
    for line in fm_text.splitlines():
        if ": " in line:
            k, v = line.split(": ", 1)
            meta[k.strip()] = v.strip()
    return meta, body


def write_frontmatter(path: Path, data: dict[str, str], body: str) -> None:
    """Serialize key:value pairs as frontmatter, write with body."""
    lines = ["---"]
    for k, v in data.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append(body)
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# HTML marker extraction / replacement
# ---------------------------------------------------------------------------


def extract_between_markers(text: str, tag: str) -> str | None:
    """Content between <!-- tag --> and <!-- /tag -->. Returns None if not found."""
    pattern = re.compile(
        rf"<!--\s*{re.escape(tag)}\s*-->\s*\n?(.*?)\s*<!--\s*/{re.escape(tag)}\s*-->",
        re.DOTALL,
    )
    m = pattern.search(text)
    return m.group(1).strip() if m else None


def replace_between_markers(text: str, tag: str, content: str) -> str:
    """Replace content between <!-- tag --> and <!-- /tag -->."""
    pattern = re.compile(
        rf"(<!--\s*{re.escape(tag)}\s*-->\s*\n?).*?(\s*<!--\s*/{re.escape(tag)}\s*-->)",
        re.DOTALL,
    )
    return pattern.sub(rf"\g<1>{content}\n\g<2>", text)


# ---------------------------------------------------------------------------
# Heading-based section fallback
# ---------------------------------------------------------------------------


def extract_heading_section(body: str, heading: str) -> str | None:
    """Extract text under a ## heading until the next ## or EOF."""
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(body)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# Section helper (marker with heading fallback)
# ---------------------------------------------------------------------------


def section(body: str, tag: str, heading: str | None = None) -> str:
    """Extract content from marker or heading fallback."""
    text_from_marker = extract_between_markers(body, tag)
    if text_from_marker is not None:
        return text_from_marker
    if heading:
        text_from_heading = extract_heading_section(body, heading)
        if text_from_heading is not None:
            return text_from_heading
    return ""


# ---------------------------------------------------------------------------
# File list parsing
# ---------------------------------------------------------------------------


def parse_file_list(text: str) -> list[str]:
    """Parse markdown list items as file paths."""
    paths: list[str] = []
    for line in text.splitlines():
        line = line.strip()  # noqa: PLW2901
        if line.startswith("- "):
            path = line[2:].strip()
            link_match = re.match(r"\[.*?\]\((.+?)\)", path)
            if link_match:
                path = link_match.group(1)
            if path:
                paths.append(path)
    return paths


# ---------------------------------------------------------------------------
# Renderer: structured data → protocol markdown files
# ---------------------------------------------------------------------------


def _slugify(text: str) -> str:
    """Convert text to a filename-safe slug."""
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    return (slug or "step")[:60]


def _render_task_item(item: dict[str, Any], indent: int = 0) -> str:
    """Render a single TaskItem as markdown checkbox with optional body and subtasks."""
    prefix = "  " * indent
    lines = [f"{prefix}- [ ] {item['title']}"]

    body = item.get("body", "").strip()
    if body:
        for body_line in body.splitlines():
            lines.append(f"{prefix}  {body_line}" if body_line.strip() else "")

    for sub in item.get("subtasks", []):
        lines.append(_render_task_item(sub, indent + 1))

    return "\n".join(lines)


def _render_task(task: dict[str, Any]) -> str:
    """Render a single Task block with <!-- task --> markers."""
    parts = ["<!-- task -->", f"### {task['heading']}"]

    description = task.get("description", "").strip()
    if description:
        parts.append("")
        parts.append(description)

    for subtask in task.get("subtasks", []):
        parts.append("")
        parts.append(_render_task_item(subtask))

    criteria = task.get("acceptance_criteria", [])
    if criteria:
        parts.append("")
        parts.append("<!-- accept -->")
        for c in criteria:
            parts.append(f"- {c}")
        parts.append("<!-- /accept -->")

    parts.append("<!-- /task -->")
    return "\n".join(parts)


def render_step_body(step: dict[str, Any]) -> str:
    """Render step file body (without frontmatter) from StepDef dict."""
    parts: list[str] = [f"# {step['name']}"]

    # Objective
    parts.append("")
    parts.append("## Objective")
    parts.append("")
    parts.append("<!-- objective -->")
    parts.append(step["objective"])
    parts.append("<!-- /objective -->")

    # Tasks
    parts.append("")
    parts.append("## Tasks")
    parts.append("")
    parts.append("<!-- tasks -->")
    for task in step.get("tasks", []):
        parts.append("")
        parts.append(_render_task(task))
    parts.append("")
    parts.append("<!-- /tasks -->")

    # Constraints
    constraints = step.get("constraints", [])
    if constraints:
        parts.append("")
        parts.append("## Constraints")
        parts.append("")
        parts.append("<!-- constraints -->")
        for c in constraints:
            parts.append(f"- {c}")
        parts.append("<!-- /constraints -->")

    # Implementation Notes
    impl_notes = step.get("impl_notes", "").strip()
    if impl_notes:
        parts.append("")
        parts.append("## Implementation Notes")
        parts.append("")
        parts.append(impl_notes)

    # Verification
    verification = step.get("verification", [])
    if verification:
        parts.append("")
        parts.append("## Verification")
        parts.append("")
        parts.append("<!-- verification -->")
        parts.append("```bash")
        for cmd in verification:
            parts.append(cmd)
        parts.append("```")
        parts.append("<!-- /verification -->")

    # Context
    context_inline = step.get("context_inline", "")
    context_files = step.get("context_files", [])
    if context_inline or context_files:
        parts.append("")
        parts.append("## Context")
        parts.append("")
    if context_inline:
        parts.append("<!-- context:inline -->")
        parts.append(context_inline)
        parts.append("<!-- /context:inline -->")
        if context_files:
            parts.append("")
    if context_files:
        parts.append("<!-- context:files -->")
        for ctx_file in context_files:
            parts.append(f"- {ctx_file}")
        parts.append("<!-- /context:files -->")

    # Starting Points
    starting_points = step.get("starting_points", [])
    if starting_points:
        parts.append("")
        parts.append("## Starting Points")
        parts.append("")
        parts.append("<!-- starting_points -->")
        for sp in starting_points:
            parts.append(f"- {sp}")
        parts.append("<!-- /starting_points -->")

    # Findings (always present, empty)
    parts.append("")
    parts.append("## Findings")
    parts.append("")
    parts.append("<!-- findings -->")
    parts.append("<!-- /findings -->")

    # Memory Bank Impact
    mb_impact = step.get("memory_bank_impact", [])
    if mb_impact:
        parts.append("")
        parts.append("## Memory Bank Impact")
        parts.append("")
        for item in mb_impact:
            parts.append(f"- [ ] {item}")
    else:
        parts.append("")
        parts.append("## Memory Bank Impact")
        parts.append("")
        parts.append("- [ ] None expected")

    parts.append("")
    return "\n".join(parts)


def render_step_file(step: dict[str, Any], step_id: str) -> str:
    """Render a complete step file (frontmatter + body) from StepDef dict."""
    fm_lines = [
        "---",
        f"id: {step_id}",
        "status: pending",
        f"estimate: {step.get('estimate', '1h')}",
        "---",
    ]
    body = render_step_body(step)
    return "\n".join(fm_lines) + "\n" + body


def render_plan_md(protocol: dict[str, Any], item_entries: list[dict[str, str]], today: str | None = None) -> str:
    """Render plan.md from protocol data and resolved item entries.

    item_entries: list of {"name": str, "path": str, "id": str, "estimate": str, "group"?: str}
    """
    today = today or date.today().isoformat()

    parts: list[str] = [
        "---",
        "status: Draft",
        "---",
        f"# Protocol: {protocol['name']}",
        "",
        "**Status**: Draft",
        f"**Created**: {today}",
        "**PRD**: [./prd.md](./prd.md)",
        "",
        "## Context",
        "",
        protocol["context"],
        "",
        "## Decision",
        "",
        protocol["decision"],
        "",
        "## Rationale",
        "",
        protocol["rationale"],
        "",
        "## Consequences",
        "",
        "### Positive",
        "",
    ]
    for p in protocol.get("consequences_positive", []):
        parts.append(f"- {p}")

    parts.append("")
    parts.append("### Negative")
    parts.append("")
    for n in protocol.get("consequences_negative", []):
        parts.append(f"- {n}")

    parts.append("")
    parts.append("## Progress")

    current_group: str | None = None
    for entry in item_entries:
        group = entry.get("group")
        if group and group != current_group:
            parts.append("")
            parts.append(f"### {group}")
            current_group = group
        elif not group and current_group is not None:
            current_group = None

        parts.append("")
        parts.append(
            f"- [ ] [{entry['name']}](./{entry['path']}) "
            f"<!-- id:{entry['id']} --> — {entry['estimate']} est"
        )

    parts.append("")
    return "\n".join(parts)


def render_protocol(protocol: dict[str, Any], output_dir: str | Path, today: str | None = None) -> dict[str, Any]:
    """Render a complete protocol directory from structured data.

    Creates step files and plan.md in output_dir. Does NOT create prd.md
    (that's expected to already exist or be handled separately).

    Returns {"files_created": [...], "step_count": N}.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    item_entries: list[dict[str, str]] = []
    files_created: list[str] = []
    item_num = 0

    for raw_item in protocol.get("items", []):
        # Support both direct format ({"steps": [...]}) and ItemWrapper
        # format ({"type": "group", "group": {...}}) from Pydantic schema
        if "type" in raw_item:
            item = raw_item.get("group") or raw_item.get("step") or raw_item
        else:
            item = raw_item

        item_num += 1
        prefix = f"{item_num:02d}"

        if "steps" in item:
            # GroupDef
            group_title = item["title"]
            group_slug = _slugify(group_title)
            group_dir_name = f"{prefix}-{group_slug}"
            group_dir = output_dir / group_dir_name
            group_dir.mkdir(parents=True, exist_ok=True)

            for step_idx, step in enumerate(item["steps"], 1):
                step_prefix = f"{step_idx:02d}"
                step_slug = _slugify(step["name"])
                step_filename = f"{step_prefix}-{step_slug}.md"
                step_id = f"{group_dir_name}-{step_prefix}-{step_slug}"
                step_path = group_dir / step_filename

                content = render_step_file(step, step_id)
                step_path.write_text(content, encoding="utf-8")

                rel_path = f"{group_dir_name}/{step_filename}"
                files_created.append(rel_path)
                item_entries.append({
                    "name": step["name"],
                    "path": rel_path,
                    "id": step_id,
                    "estimate": step.get("estimate", "1h"),
                    "group": f"{group_title} ({group_dir_name}/)",
                })
        else:
            # StepDef
            step_slug = _slugify(item["name"])
            step_filename = f"{prefix}-{step_slug}.md"
            step_id = f"{prefix}-{step_slug}"
            step_path = output_dir / step_filename

            content = render_step_file(item, step_id)
            step_path.write_text(content, encoding="utf-8")

            files_created.append(step_filename)
            item_entries.append({
                "name": item["name"],
                "path": step_filename,
                "id": step_id,
                "estimate": item.get("estimate", "1h"),
            })

    # Render plan.md
    plan_content = render_plan_md(protocol, item_entries, today)
    (output_dir / "plan.md").write_text(plan_content, encoding="utf-8")
    files_created.append("plan.md")

    return {"files_created": files_created, "step_count": len(item_entries)}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Protocol markdown tools")
    sub = parser.add_subparsers(dest="command")

    p_render = sub.add_parser("render-protocol", help="Render protocol from JSON")
    p_render.add_argument("json_path_or_dir", help="Path to JSON file, or output dir when using --stdin")
    p_render.add_argument("output_dir", nargs="?", default=None, help="Output directory (required with file path, omitted with --stdin)")
    p_render.add_argument("--stdin", action="store_true", help="Read JSON from stdin instead of file")
    p_render.add_argument("--today", help="Override date (YYYY-MM-DD)")

    args = parser.parse_args()

    if args.command == "render-protocol":
        if args.stdin:
            protocol = json.loads(sys.stdin.read())
            out_dir = args.json_path_or_dir  # first positional arg is output_dir in stdin mode
        else:
            with open(args.json_path_or_dir, encoding="utf-8") as fh:
                protocol = json.load(fh)
            out_dir = args.output_dir
        result = render_protocol(protocol, out_dir, today=args.today)
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    _cli()
