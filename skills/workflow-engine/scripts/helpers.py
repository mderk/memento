"""Protocol markdown parsing utilities for the workflow engine.

Provides functions for reading and updating protocol plan.md and step files,
including marker management ([x], [~], [ ]) and findings sections.
"""

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


class PlanStep(BaseModel):
    """A step parsed from plan.md progress section."""

    text: str
    marker: str  # "[ ]", "[x]", "[~]", "[-]"
    link: str | None = None
    estimate: str | None = None


class StepFile(BaseModel):
    """Parsed content from a protocol step file."""

    subtasks: list[dict[str, str]] = []
    context: str = ""
    findings: str = ""
    implementation_notes: str = ""


# ---------------------------------------------------------------------------
# Plan parsing
# ---------------------------------------------------------------------------

_MARKER_RE = re.compile(r"^(\s*)-\s+\[([ x~\-])\]\s+(.+)$")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_ESTIMATE_RE = re.compile(r"—\s*(.+)$")


def parse_plan_md(path: str | Path) -> list[PlanStep]:
    """Parse a protocol plan.md and return list of steps with status markers.

    Looks for lines matching: - [x] [Step Name](./path.md) — estimate
    """
    path = Path(path)
    if not path.is_file():
        return []

    text = path.read_text(encoding="utf-8")
    steps: list[PlanStep] = []

    for line in text.splitlines():
        m = _MARKER_RE.match(line)
        if not m:
            continue

        marker = f"[{m.group(2)}]"
        rest = m.group(3).strip()

        # Extract link if present
        link_match = _LINK_RE.search(rest)
        link = link_match.group(2) if link_match else None

        # Extract estimate if present
        est_match = _ESTIMATE_RE.search(rest)
        estimate = est_match.group(1).strip() if est_match else None

        steps.append(PlanStep(
            text=rest,
            marker=marker,
            link=link,
            estimate=estimate,
        ))

    return steps


# ---------------------------------------------------------------------------
# Step file parsing
# ---------------------------------------------------------------------------

_SUBTASK_RE = re.compile(r"^\s*-\s+\[([ x~\-])\]\s+(.+)$")


def parse_step_file(path: str | Path) -> StepFile:
    """Parse a protocol step file, extracting subtasks, context, and findings."""
    path = Path(path)
    if not path.is_file():
        return StepFile()

    text = path.read_text(encoding="utf-8")
    result = StepFile()

    # Split into sections by ## headers
    sections: dict[str, str] = {}
    current_header = ""
    current_lines: list[str] = []

    for line in text.splitlines():
        if line.startswith("## "):
            if current_header:
                sections[current_header] = "\n".join(current_lines)
            current_header = line[3:].strip().lower()
            current_lines = []
        else:
            current_lines.append(line)

    if current_header:
        sections[current_header] = "\n".join(current_lines)

    # Extract subtasks from "tasks" section
    tasks_text = sections.get("tasks", "")
    for line in tasks_text.splitlines():
        m = _SUBTASK_RE.match(line)
        if m:
            result.subtasks.append({
                "marker": f"[{m.group(1)}]",
                "description": m.group(2).strip(),
            })

    result.context = sections.get("context", "").strip()
    result.findings = sections.get("findings", "").strip()
    result.implementation_notes = sections.get("implementation notes", "").strip()

    return result


# ---------------------------------------------------------------------------
# Marker updates
# ---------------------------------------------------------------------------


def update_marker(path: str | Path, item_text: str, new_marker: str) -> bool:
    """Replace a marker ([ ], [x], [~], [-]) for a matching item in a markdown file.

    Args:
        path: Path to the markdown file.
        item_text: Text to match (partial match on the line after the marker).
        new_marker: New marker string, e.g. "[x]" or "[~]".

    Returns:
        True if a replacement was made, False otherwise.
    """
    path = Path(path)
    if not path.is_file():
        return False

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    found = False

    for i, line in enumerate(lines):
        m = _MARKER_RE.match(line)
        if m and item_text in m.group(3):
            old_marker = f"[{m.group(2)}]"
            lines[i] = line.replace(old_marker, new_marker, 1)
            found = True
            break

    if found:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return found


# ---------------------------------------------------------------------------
# Findings management
# ---------------------------------------------------------------------------


def append_findings(path: str | Path, findings: str) -> None:
    """Append text to the ## Findings section of a markdown file.

    Creates the section if it doesn't exist.
    """
    path = Path(path)
    if not path.is_file():
        return

    text = path.read_text(encoding="utf-8")

    if "## Findings" in text:
        # Append to existing section
        idx = text.index("## Findings")
        # Find the end of the findings section (next ## or end of file)
        rest = text[idx + len("## Findings"):]
        next_section = rest.find("\n## ")
        if next_section == -1:
            text = text.rstrip() + "\n\n" + findings.strip() + "\n"
        else:
            insert_at = idx + len("## Findings") + next_section
            text = text[:insert_at].rstrip() + "\n\n" + findings.strip() + "\n" + text[insert_at:]
    else:
        text = text.rstrip() + "\n\n## Findings\n\n" + findings.strip() + "\n"

    path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Context loading
# ---------------------------------------------------------------------------


def load_context_files(protocol_dir: str | Path, step_path: str) -> str:
    """Load shared _context/ files for a protocol step.

    Replicates the logic from load-context.py:
    - If step is in a group folder, load group _context/ first
    - Then load protocol-wide _context/
    """
    protocol_dir = Path(protocol_dir)
    step_parts = Path(step_path).parts
    files: list[Path] = []

    # Group context (if step is in a group folder)
    if len(step_parts) > 1:
        group_ctx = protocol_dir / step_parts[0] / "_context"
        if group_ctx.is_dir():
            files.extend(sorted(
                f for f in group_ctx.iterdir()
                if f.is_file() and f.suffix == ".md"
            ))

    # Protocol-wide context
    proto_ctx = protocol_dir / "_context"
    if proto_ctx.is_dir():
        files.extend(sorted(
            f for f in proto_ctx.iterdir()
            if f.is_file() and f.suffix == ".md"
        ))

    if not files:
        return ""

    parts: list[str] = []
    for f in files:
        rel = f.relative_to(protocol_dir)
        parts.append(f"-- {rel} --")
        parts.append(f.read_text(encoding="utf-8"))
        parts.append("")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# CLI interface (for use from ShellStep)
# ---------------------------------------------------------------------------

def _cli() -> None:
    """Minimal CLI for shell-step invocation."""
    import argparse
    import json as _json
    import sys

    parser = argparse.ArgumentParser(description="Workflow engine helpers")
    sub = parser.add_subparsers(dest="command")

    # parse-protocol
    p_parse = sub.add_parser("parse-protocol")
    p_parse.add_argument("protocol_dir")

    # update-marker
    p_marker = sub.add_parser("update-marker")
    p_marker.add_argument("file")
    p_marker.add_argument("text")
    p_marker.add_argument("marker")

    # append-findings
    p_findings = sub.add_parser("append-findings")
    p_findings.add_argument("file")
    p_findings.add_argument("findings")

    # load-context
    p_ctx = sub.add_parser("load-context")
    p_ctx.add_argument("protocol_dir")
    p_ctx.add_argument("step_path")

    args = parser.parse_args()

    if args.command == "parse-protocol":
        plan_path = Path(args.protocol_dir) / "plan.md"
        steps = parse_plan_md(plan_path)
        out: dict[str, Any] = {
            "steps": [
                {"text": s.text, "marker": s.marker, "link": s.link, "estimate": s.estimate}
                for s in steps
            ],
            "pending_steps": [
                {"text": s.text, "marker": s.marker, "link": s.link, "estimate": s.estimate}
                for s in steps if s.marker in ("[ ]", "[~]")
            ],
        }
        print(_json.dumps(out, indent=2))

    elif args.command == "update-marker":
        ok = update_marker(args.file, args.text, args.marker)
        print(_json.dumps({"updated": ok}))

    elif args.command == "append-findings":
        append_findings(args.file, args.findings)
        print(_json.dumps({"appended": True}))

    elif args.command == "load-context":
        content = load_context_files(args.protocol_dir, args.step_path)
        print(content)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    _cli()
