# ruff: noqa: E501, T201
"""Protocol v2 parsing utilities for the workflow engine.

Frontmatter + HTML marker based step discovery, rendering, and status tracking.
Markdown primitives imported from protocol_md.py; this module adds protocol-specific
workflow logic (discover, prepare, render, findings, status).
"""

import argparse
import importlib.util
import json
import re
import sys
import types
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Import shared markdown primitives from protocol_md.py
# ---------------------------------------------------------------------------

def _import_sibling(name: str) -> types.ModuleType:
    """Import a Python module from the same directory as this file."""
    p = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, p)
    if not spec or not spec.loader:
        raise ImportError(f"Cannot load sibling module {name!r} from {p}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_pm = _import_sibling("protocol_md")

# Re-export markdown primitives for backward compatibility
read_frontmatter = _pm.read_frontmatter
write_frontmatter = _pm.write_frontmatter
extract_between_markers = _pm.extract_between_markers
replace_between_markers = _pm.replace_between_markers
_extract_heading_section = _pm.extract_heading_section


# ---------------------------------------------------------------------------
# Step discovery
# ---------------------------------------------------------------------------


def _parse_plan_progress_ids(plan_path: Path) -> list[str]:
    """Extract step ids from plan.md progress markers: <!-- id:xxx -->."""
    if not plan_path.is_file():
        return []
    text = plan_path.read_text(encoding="utf-8")
    return re.findall(r"<!--\s*id:(\S+)\s*-->", text)


def discover_steps(protocol_dir: str | Path) -> dict[str, Any]:
    """Discover step files by frontmatter id.

    Returns {"all_steps": [...], "pending_steps": [...]} where each entry has
    id, path (relative to protocol_dir), and status.
    Ordering: prefer plan.md progress id order, fallback to path sort.
    """
    protocol_dir = Path(protocol_dir)
    plan_path = protocol_dir / "plan.md"
    plan_ids = _parse_plan_progress_ids(plan_path)

    # Collect all step files with frontmatter id
    steps_by_id: dict[str, dict[str, str]] = {}
    for md_file in sorted(protocol_dir.rglob("*.md")):
        if md_file.name.startswith("_") or md_file.name == "plan.md" or md_file.name == "prd.md":
            continue
        # Skip files inside _context/ directories
        if "_context" in md_file.parts:
            continue
        fm, _ = read_frontmatter(md_file)
        step_id = fm.get("id")
        if not step_id:
            continue
        status = fm.get("status", "pending")
        rel = str(md_file.relative_to(protocol_dir))
        steps_by_id[step_id] = {"id": step_id, "path": rel, "status": status}

    # Order by plan.md progress ids first, then path-sorted remainder
    ordered: list[dict[str, str]] = []
    seen: set[str] = set()
    for sid in plan_ids:
        if sid in steps_by_id and sid not in seen:
            ordered.append(steps_by_id[sid])
            seen.add(sid)
    for sid in sorted(steps_by_id.keys(), key=lambda s: steps_by_id[s]["path"]):
        if sid not in seen:
            ordered.append(steps_by_id[sid])
            seen.add(sid)

    pending = [s for s in ordered if s["status"] in ("pending", "in-progress")]
    return {"all_steps": ordered, "pending_steps": pending}


# ---------------------------------------------------------------------------
# Task rendering
# ---------------------------------------------------------------------------

# Use shared section helper from protocol_md
_section = _pm.section


def render_task_full(step_path: str | Path) -> str:
    """Deterministically render full developer prompt from step markers."""
    step_path = Path(step_path)
    _, body = read_frontmatter(step_path)

    parts: list[str] = []

    objective = _section(body, "objective", "Objective")
    if objective:
        parts.append(f"## Objective\n\n{objective}")

    tasks = _section(body, "tasks", "Tasks")
    if tasks:
        parts.append(f"## Tasks\n\n{tasks}")

    constraints = _section(body, "constraints", "Constraints")
    if constraints:
        parts.append(f"## Constraints\n\n{constraints}")

    context_inline = _section(body, "context:inline", "Context")
    if context_inline:
        parts.append(f"## Context\n\n{context_inline}")

    context_files = _section(body, "context:files")
    if context_files:
        parts.append(f"## Context Files\n\n{context_files}")

    starting_points = _section(body, "starting_points", "Starting Points")
    if starting_points:
        parts.append(f"## Starting Points\n\n{starting_points}")

    verification = _section(body, "verification", "Verification")
    if verification:
        parts.append(f"## Verification\n\n{verification}")

    impl_notes = _extract_heading_section(body, "Implementation Notes")
    if impl_notes:
        parts.append(f"## Implementation Notes\n\n{impl_notes}")

    return "\n\n".join(parts)


def render_task_compact(step_path: str | Path) -> str:
    """Render compact prompt (objective + tasks + constraints + refs)."""
    step_path = Path(step_path)
    _, body = read_frontmatter(step_path)

    parts: list[str] = []

    objective = _section(body, "objective", "Objective")
    if objective:
        parts.append(f"## Objective\n\n{objective}")

    tasks = _section(body, "tasks", "Tasks")
    if tasks:
        parts.append(f"## Tasks\n\n{tasks}")

    constraints = _section(body, "constraints", "Constraints")
    if constraints:
        parts.append(f"## Constraints\n\n{constraints}")

    context_files = _section(body, "context:files")
    if context_files:
        parts.append(f"## Context Files\n\n{context_files}")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# prepare_step
# ---------------------------------------------------------------------------


_parse_file_list = _pm.parse_file_list


def _parse_verification_commands(text: str) -> list[str | dict[str, str | int]]:
    """Extract shell commands from fenced code blocks in the verification section.

    Supports optional timeout prefix: ``# timeout:120 cmd`` or ``timeout:60 cmd``.
    A standalone ``# timeout:N`` on its own line applies to the next command.
    Returns a list of strings (plain commands) or dicts ({"cmd": ..., "timeout": N}).
    """
    commands: list = []
    in_code_block = False
    pending_timeout: int | None = None
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            if not in_code_block:
                pending_timeout = None  # reset at block boundary
            continue
        if in_code_block:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                # Check for timeout directive with inline command: # timeout:N cmd
                m = re.match(r"^#\s*timeout:(\d+)\s+(.+)$", stripped)
                if m:
                    commands.append({"cmd": m.group(2), "timeout": int(m.group(1))})
                    pending_timeout = None
                else:
                    # Check for standalone timeout: # timeout:N
                    m = re.match(r"^#\s*timeout:(\d+)\s*$", stripped)
                    if m:
                        pending_timeout = int(m.group(1))
                continue
            # Check for inline timeout prefix: timeout:N cmd
            m = re.match(r"^timeout:(\d+)\s+(.+)$", stripped)
            if m:
                commands.append({"cmd": m.group(2), "timeout": int(m.group(1))})
                pending_timeout = None
            elif pending_timeout is not None:
                commands.append({"cmd": stripped, "timeout": pending_timeout})
                pending_timeout = None
            else:
                commands.append(stripped)
    return commands


def _extract_accept_criteria(text: str) -> list[str]:
    """Extract bulleted list items from <!-- accept --> ... <!-- /accept --> block."""
    m = re.search(r'<!--\s*accept\s*-->(.*?)<!--\s*/accept\s*-->', text, re.DOTALL)
    if not m:
        return []
    criteria = []
    for line in m.group(1).splitlines():
        stripped = line.strip()
        bullet_m = re.match(r'^-\s+(.+)$', stripped)
        if bullet_m:
            criteria.append(bullet_m.group(1).strip())
    return criteria


def _parse_task_groups(tasks_text: str | None, step_id: str) -> list[dict[str, Any]]:
    """Group tasks by ### headings — each group becomes one TDD unit.

    If no ### headings, the entire tasks block is one unit.
    Returns PlanTask-shaped dicts with description = heading + subtasks.
    Extracts <!-- accept --> blocks for acceptance_criteria before stripping markers.
    """
    if not tasks_text or not tasks_text.strip():
        return [{"id": step_id, "description": step_id, "acceptance_criteria": [], "depends_on": []}]

    # Split by <!-- task --> / <!-- /task --> markers first to extract accept blocks per task
    task_marker_re = re.compile(r'<!--\s*task\s*-->(.*?)<!--\s*/task\s*-->', re.DOTALL)
    task_blocks = task_marker_re.findall(tasks_text)

    if task_blocks:
        # Parse each task block individually
        units: list[dict[str, Any]] = []
        for idx, block in enumerate(task_blocks):
            criteria = _extract_accept_criteria(block)
            # Strip accept blocks and task markers before parsing headings
            accept_re = re.compile(r'<!--\s*accept\s*-->.*?<!--\s*/accept\s*-->', re.DOTALL)
            clean_block = accept_re.sub('', block).strip()
            if not clean_block:
                continue
            # Extract heading
            lines = clean_block.splitlines()
            heading = ""
            body_lines = []
            for line in lines:
                if line.strip().startswith("###") and not heading:
                    heading = line.strip()
                else:
                    body_lines.append(line)
            body = "\n".join(body_lines).strip()
            description = f"{heading}\n\n{body}" if heading else body
            if not description.strip():
                continue
            units.append({
                "id": f"g{idx + 1}",
                "description": description.strip(),
                "acceptance_criteria": criteria,
                "depends_on": [],
            })
        return units

    # No <!-- task --> markers — fall back to heading-based grouping
    lines = tasks_text.splitlines()
    groups: list[tuple[str, list[str]]] = []
    current_heading = ""
    current_lines: list[str] = []

    for line in lines:
        if line.strip().startswith("###"):
            if current_heading or current_lines:
                groups.append((current_heading, current_lines))
            current_heading = line.strip()
            current_lines = []
        else:
            current_lines.append(line)

    # Flush last group
    if current_heading or current_lines:
        groups.append((current_heading, current_lines))

    if not groups:
        return [{"id": step_id, "description": tasks_text.strip(), "acceptance_criteria": [], "depends_on": []}]

    units = []
    for idx, (heading, body_lines) in enumerate(groups):
        body = "\n".join(body_lines).strip()
        description = f"{heading}\n\n{body}" if heading else body
        if not description.strip():
            continue
        units.append({
            "id": f"g{idx + 1}",
            "description": description.strip(),
            "acceptance_criteria": [],
            "depends_on": [],
        })
    return units


def parse_units_from_tasks(tasks_text: str) -> list[dict[str, Any]]:
    """Extract checklist items from <!-- tasks --> content as PlanTask-shaped dicts.

    Supports <!-- accept --> blocks after checklist items to attach acceptance_criteria.
    """
    if not tasks_text or not tasks_text.strip():
        return []
    units: list[dict[str, Any]] = []
    idx = 0
    lines = tasks_text.splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        m = re.match(r"^-\s+\[[ x~]\]\s+(.+)$", stripped)
        if not m:
            i += 1
            continue
        idx += 1
        description = m.group(1).strip()
        # Strip <!-- id:xxx --> markers from description
        description = re.sub(r"\s*<!--\s*id:\S+\s*-->\s*", "", description).strip()
        i += 1
        # Collect remaining lines until next checklist item for accept block extraction
        lookahead_start = i
        while i < len(lines):
            if re.match(r"^\s*-\s+\[[ x~]\]\s+", lines[i].strip()):
                break
            i += 1
        lookahead_text = "\n".join(lines[lookahead_start:i])
        criteria = _extract_accept_criteria(lookahead_text)
        units.append({
            "id": f"t{idx}",
            "description": description,
            "acceptance_criteria": criteria,
            "depends_on": [],
        })
    return units


def prepare_step(protocol_dir: str | Path, step_path: str | Path) -> dict[str, Any]:
    """Prepare step data for the development subworkflow."""
    protocol_dir = Path(protocol_dir).resolve()
    step_path = Path(step_path)

    # Resolve step_path relative to protocol_dir if not absolute
    if not step_path.is_absolute():
        step_path = (protocol_dir / step_path).resolve()
    else:
        step_path = step_path.resolve()

    # Guard against path traversal (e.g. ../../etc/passwd)
    try:
        step_path.relative_to(protocol_dir)
    except ValueError as exc:
        raise ValueError(
            f"step_path {step_path} is outside protocol_dir {protocol_dir}"
        ) from exc

    fm, body = read_frontmatter(step_path)

    task_full = render_task_full(step_path)
    task_compact = render_task_compact(step_path)

    # Parse structured lists
    context_files_text = _section(body, "context:files")
    context_files = _parse_file_list(context_files_text) if context_files_text else []

    mb_refs = [f for f in context_files if ".memory_bank" in f or "memory_bank" in f]
    non_mb_context = [f for f in context_files if f not in mb_refs]

    starting_points_text = _section(body, "starting_points", "Starting Points")
    starting_points = _parse_file_list(starting_points_text) if starting_points_text else []

    verification_text = _section(body, "verification", "Verification")
    verification_commands = _parse_verification_commands(verification_text) if verification_text else []

    # Group tasks by ### headings — each group = one unit in the TDD loop.
    # If no ### headings, the entire tasks block is one unit.
    tasks_text = _section(body, "tasks", "Tasks")
    units = _parse_task_groups(tasks_text, fm.get("id", "step"))

    return {
        "id": fm.get("id", ""),
        "step_file": str(step_path),
        "task_full_md": task_full,
        "task_compact_md": task_compact,
        "context_files": non_mb_context,
        "mb_refs": mb_refs,
        "starting_points": starting_points,
        "verification_commands": verification_commands,
        "units": units,
    }


# ---------------------------------------------------------------------------
# Findings management (append + dedupe)
# ---------------------------------------------------------------------------


def _normalize_finding(text: str) -> str:
    """Normalize a finding line for dedup comparison."""
    return re.sub(r"\s+", " ", text.strip().lower())


def record_findings(step_path: str | Path, findings_json: str) -> None:  # noqa: C901 — inherent complexity of dedupe+merge
    """Append findings into the <!-- findings --> block with dedupe.

    findings_json: JSON array of {"tag": "DECISION", "text": "..."} objects,
    or a JSON string (from DevelopResult).
    """
    step_path = Path(step_path)
    if not step_path.is_file():
        return

    # Parse input
    try:
        findings = json.loads(findings_json)
    except (json.JSONDecodeError, TypeError):
        return

    if isinstance(findings, dict):
        findings = findings.get("findings", [])
    if not isinstance(findings, list) or not findings:
        return

    text = step_path.read_text(encoding="utf-8")

    # Get existing findings
    existing_raw = extract_between_markers(text, "findings") or ""
    existing_normalized = {_normalize_finding(line) for line in existing_raw.splitlines() if line.strip()}

    # Build new lines
    new_lines: list[str] = []
    for f in findings:
        if isinstance(f, dict):
            tag = f.get("tag", "").upper()
            ftxt = f.get("text", "")
            line = f"- [{tag}] {ftxt}" if tag else f"- {ftxt}"
        elif isinstance(f, str):
            line = f"- {f}"
        else:
            continue
        if _normalize_finding(line) not in existing_normalized:
            new_lines.append(line)

    if not new_lines:
        return

    # Append to existing
    updated_content = existing_raw
    if updated_content and not updated_content.endswith("\n"):
        updated_content += "\n"
    updated_content += "\n".join(new_lines)

    text = replace_between_markers(text, "findings", updated_content)
    step_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Status management
# ---------------------------------------------------------------------------


def update_status(step_path: str | Path, new_status: str) -> None:
    """Update frontmatter status + sync plan.md marker by step id."""
    step_path = Path(step_path)
    if not step_path.is_file():
        return

    fm, body = read_frontmatter(step_path)
    step_id = fm.get("id")
    if not step_id:
        return

    fm["status"] = new_status
    write_frontmatter(step_path, fm, body)

    # Sync plan.md (walk up at most 5 levels to find it)
    protocol_dir = step_path.parent
    for _ in range(5):
        if protocol_dir == protocol_dir.parent:
            break
        plan_path = protocol_dir / "plan.md"
        if plan_path.is_file():
            _sync_plan_marker(plan_path, step_id, new_status)
            break
        protocol_dir = protocol_dir.parent


_STATUS_TO_MARKER = {
    "pending": "[ ]",
    "in-progress": "[~]",
    "done": "[x]",
    "blocked": "[-]",
}

_MARKER_RE = re.compile(r"^(\s*-\s+)\[([ x~\-])\](.+?)$")


def _sync_plan_marker(plan_path: Path, step_id: str, status: str) -> None:
    """Update the marker in plan.md for the line containing <!-- id:step_id -->."""
    new_marker = _STATUS_TO_MARKER.get(status)
    if not new_marker:
        return

    text = plan_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    id_pattern = f"<!-- id:{step_id} -->"

    for i, line in enumerate(lines):
        if id_pattern in line:
            m = _MARKER_RE.match(line)
            if m:
                old = f"[{m.group(2)}]"
                lines[i] = line.replace(old, new_marker, 1)
                break

    plan_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# update_marker (kept, now id-based)
# ---------------------------------------------------------------------------


def update_marker(path: str | Path, item_id: str, new_marker: str) -> bool:
    """Replace a marker for a matching item by id (<!-- id:xxx -->) in a markdown file."""
    path = Path(path)
    if not path.is_file():
        return False

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    id_pattern = f"<!-- id:{item_id} -->"
    found = False

    for i, line in enumerate(lines):
        if id_pattern in line:
            m = _MARKER_RE.match(line)
            if m:
                old_marker = f"[{m.group(2)}]"
                lines[i] = line.replace(old_marker, new_marker, 1)
                found = True
                break

    if found:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return found


# ---------------------------------------------------------------------------
# Context loading (kept as-is)
# ---------------------------------------------------------------------------


def load_context_files(protocol_dir: str | Path, step_path: str) -> str:
    """Load shared _context/ files for a protocol step."""
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
# Migration helper (v1 → v2)
# ---------------------------------------------------------------------------


def migrate_protocol(protocol_dir: str | Path) -> dict[str, Any]:
    """Migrate old-format protocol files to v2 (frontmatter + markers).

    - Adds id/status frontmatter to step files
    - Inserts missing markers (tasks/findings/objective)
    - Adds <!-- id:... --> markers in plan.md progress section
    """
    protocol_dir = Path(protocol_dir)
    migrated: list[str] = []

    for md_file in sorted(protocol_dir.rglob("*.md")):
        if md_file.name in ("plan.md", "prd.md") or md_file.name.startswith("_"):
            continue
        if "_context" in md_file.parts:
            continue

        fm, body = read_frontmatter(md_file)

        if "id" in fm:
            continue  # Already migrated

        # Derive id from filename
        rel = md_file.relative_to(protocol_dir)
        step_id = str(rel.with_suffix("")).replace("/", "-").replace(" ", "-").lower()

        fm["id"] = step_id
        fm.setdefault("status", "pending")

        # Insert missing markers
        if "<!-- tasks -->" not in body and "## Tasks" in body:
            body = _wrap_section_with_markers(body, "Tasks", "tasks")
        if "<!-- findings -->" not in body:
            if "## Findings" in body:
                body = _wrap_section_with_markers(body, "Findings", "findings")
            else:
                body = body.rstrip() + "\n\n## Findings\n\n<!-- findings -->\n<!-- /findings -->\n"
        if "<!-- objective -->" not in body and "## Objective" in body:
            body = _wrap_section_with_markers(body, "Objective", "objective")

        write_frontmatter(md_file, fm, body)
        migrated.append(str(rel))

    # Update plan.md with id markers
    plan_path = protocol_dir / "plan.md"
    if plan_path.is_file():
        _add_plan_id_markers(plan_path, protocol_dir)

    return {"migrated": migrated}


def _wrap_section_with_markers(body: str, heading: str, tag: str) -> str:
    """Wrap content under ## heading with <!-- tag --> markers."""
    pattern = re.compile(
        rf"(^##\s+{re.escape(heading)}\s*$\n)(.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(body)
    if not m:
        return body
    section_header = m.group(1)
    section_content = m.group(2).strip()
    replacement = f"{section_header}\n<!-- {tag} -->\n{section_content}\n<!-- /{tag} -->\n"
    return body[:m.start()] + replacement + body[m.end():]


def _add_plan_id_markers(plan_path: Path, protocol_dir: Path) -> None:
    """Add <!-- id:xxx --> markers to plan.md progress lines."""
    text = plan_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    link_re = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

    for i, line in enumerate(lines):
        if "<!-- id:" in line:
            continue  # Already has id marker
        m = _MARKER_RE.match(line)
        if not m:
            continue
        link_match = link_re.search(line)
        if not link_match:
            continue
        link_path = link_match.group(2)
        # Normalize: strip leading ./
        if link_path.startswith("./"):
            link_path = link_path[2:]
        step_id = Path(link_path).with_suffix("").as_posix().replace("/", "-").replace(" ", "-").lower()
        lines[i] = f"{line} <!-- id:{step_id} -->"

    plan_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Worktree path helpers
# ---------------------------------------------------------------------------


def resolve_worktree_protocol_dir(protocol_dir: str | Path, worktree_path: str | Path) -> str:
    """Compute the protocol directory path inside the worktree.

    If protocol_dir is relative, join: worktree_path / protocol_dir.
    If absolute, make relative to cwd first, then join.
    Returns absolute resolved path string.
    """
    protocol_dir = Path(protocol_dir)
    worktree_path = Path(worktree_path)

    if protocol_dir.is_absolute():
        rel = protocol_dir.relative_to(Path.cwd())
        return str((worktree_path / rel).resolve())
    return str((worktree_path / protocol_dir).resolve())


def mark_plan_in_progress(protocol_dir: str | Path) -> dict[str, Any]:
    """Set plan.md frontmatter status to 'In Progress'.

    Does NOT git add/commit — the workflow ShellStep handles that.
    Returns {"plan_path": "..."} or {"skipped": true} if already in progress.
    """
    protocol_dir = Path(protocol_dir)
    plan_path = protocol_dir / "plan.md"
    if not plan_path.is_file():
        return {"skipped": True, "reason": "plan.md not found"}

    fm, body = read_frontmatter(plan_path)
    if fm.get("status") == "In Progress":
        return {"skipped": True, "reason": "already in progress"}

    fm["status"] = "In Progress"
    write_frontmatter(plan_path, fm, body)
    return {"plan_path": str(plan_path)}


# ---------------------------------------------------------------------------
# CLI interface (for use from ShellStep)
# ---------------------------------------------------------------------------


def _cli() -> None:
    """Minimal CLI for shell-step invocation."""

    parser = argparse.ArgumentParser(description="Protocol v2 helpers")
    sub = parser.add_subparsers(dest="command")

    # discover-steps
    p_discover = sub.add_parser("discover-steps")
    p_discover.add_argument("protocol_dir")

    # prepare-step
    p_prepare = sub.add_parser("prepare-step")
    p_prepare.add_argument("protocol_dir")
    p_prepare.add_argument("step_path")

    # record-findings
    p_findings = sub.add_parser("record-findings")
    p_findings.add_argument("step_path")
    p_findings.add_argument("findings_json", nargs="?", default="")

    # update-status
    p_status = sub.add_parser("update-status")
    p_status.add_argument("step_path")
    p_status.add_argument("new_status")

    # update-marker
    p_marker = sub.add_parser("update-marker")
    p_marker.add_argument("file")
    p_marker.add_argument("item_id")
    p_marker.add_argument("marker")

    # load-context
    p_ctx = sub.add_parser("load-context")
    p_ctx.add_argument("protocol_dir")
    p_ctx.add_argument("step_path")

    # migrate-protocol
    p_migrate = sub.add_parser("migrate-protocol")
    p_migrate.add_argument("protocol_dir")

    # parse-units
    p_units = sub.add_parser("parse-units")
    p_units.add_argument("protocol_dir")
    p_units.add_argument("step_path")

    # resolve-wt-protocol-dir
    p_wt = sub.add_parser("resolve-wt-protocol-dir")
    p_wt.add_argument("protocol_dir")
    p_wt.add_argument("worktree_path")

    # mark-plan-in-progress
    p_mip = sub.add_parser("mark-plan-in-progress")
    p_mip.add_argument("protocol_dir")

    args = parser.parse_args()

    if args.command == "discover-steps":
        result = discover_steps(args.protocol_dir)
        print(json.dumps(result, indent=2))

    elif args.command == "prepare-step":
        result = prepare_step(args.protocol_dir, args.step_path)
        print(json.dumps(result, indent=2))

    elif args.command == "record-findings":
        findings = args.findings_json
        if not findings:
            findings = sys.stdin.read()
        record_findings(args.step_path, findings)
        print(json.dumps({"recorded": True}))

    elif args.command == "update-status":
        update_status(args.step_path, args.new_status)
        print(json.dumps({"updated": True}))

    elif args.command == "update-marker":
        ok = update_marker(args.file, args.item_id, args.marker)
        print(json.dumps({"updated": ok}))

    elif args.command == "load-context":
        content = load_context_files(args.protocol_dir, args.step_path)
        print(content)

    elif args.command == "migrate-protocol":
        result = migrate_protocol(args.protocol_dir)
        print(json.dumps(result, indent=2))

    elif args.command == "parse-units":
        result = prepare_step(args.protocol_dir, args.step_path)
        print(json.dumps(result["units"], indent=2))

    elif args.command == "resolve-wt-protocol-dir":
        wt_dir = resolve_worktree_protocol_dir(args.protocol_dir, args.worktree_path)
        print(json.dumps({"worktree_protocol_dir": wt_dir}))

    elif args.command == "mark-plan-in-progress":
        result = mark_plan_in_progress(args.protocol_dir)
        print(json.dumps(result))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    _cli()
