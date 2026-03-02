"""Tests for workflow engine helpers (markdown parsing utilities)."""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "workflow-engine"
    / "scripts"
    / "helpers.py"
)

# Load functions directly for unit tests
_code = SCRIPT.read_text()
_ns: dict = {}
exec(compile(_code, str(SCRIPT), "exec"), _ns)

parse_plan_md = _ns["parse_plan_md"]
parse_step_file = _ns["parse_step_file"]
update_marker = _ns["update_marker"]
append_findings = _ns["append_findings"]
load_context_files = _ns["load_context_files"]


# ============ parse_plan_md ============


class TestParsePlanMd:
    def test_basic_steps(self, tmp_path):
        plan = tmp_path / "plan.md"
        plan.write_text(
            "# Plan\n\n"
            "## Progress\n\n"
            "- [ ] [Setup](./01-setup.md) — 2h est\n"
            "- [x] [Database](./02-db.md) — 3h est / 2h actual\n"
            "- [~] [API](./03-api.md)\n"
        )
        steps = parse_plan_md(plan)
        assert len(steps) == 3
        assert steps[0].marker == "[ ]"
        assert steps[0].link == "./01-setup.md"
        assert steps[0].estimate == "2h est"
        assert steps[1].marker == "[x]"
        assert steps[2].marker == "[~]"

    def test_no_links(self, tmp_path):
        plan = tmp_path / "plan.md"
        plan.write_text("- [ ] Just a plain step\n- [x] Another step\n")
        steps = parse_plan_md(plan)
        assert len(steps) == 2
        assert steps[0].link is None
        assert steps[0].text == "Just a plain step"

    def test_empty_file(self, tmp_path):
        plan = tmp_path / "plan.md"
        plan.write_text("# Empty plan\n\nNo steps here.\n")
        steps = parse_plan_md(plan)
        assert steps == []

    def test_nonexistent_file(self, tmp_path):
        steps = parse_plan_md(tmp_path / "nonexistent.md")
        assert steps == []

    def test_nested_group_links(self, tmp_path):
        plan = tmp_path / "plan.md"
        plan.write_text(
            "- [ ] [Database](./02-infra/01-database.md)\n"
            "- [ ] [Cache](./02-infra/02-cache.md)\n"
        )
        steps = parse_plan_md(plan)
        assert len(steps) == 2
        assert steps[0].link == "./02-infra/01-database.md"
        assert steps[1].link == "./02-infra/02-cache.md"

    def test_blocked_marker(self, tmp_path):
        plan = tmp_path / "plan.md"
        plan.write_text("- [-] [Blocked step](./blocked.md)\n")
        steps = parse_plan_md(plan)
        assert len(steps) == 1
        assert steps[0].marker == "[-]"


# ============ parse_step_file ============


class TestParseStepFile:
    def test_full_step_file(self, tmp_path):
        step = tmp_path / "03-api.md"
        step.write_text(
            "# Step 3: API Endpoints\n\n"
            "## Tasks\n\n"
            "- [ ] Create user endpoint\n"
            "- [x] Create auth endpoint\n"
            "- [~] Create profile endpoint\n\n"
            "## Context\n\n"
            "We're building a REST API.\n\n"
            "## Implementation Notes\n\n"
            "Use FastAPI router pattern.\n\n"
            "## Findings\n\n"
            "- [GOTCHA] Rate limiting already exists\n"
        )
        result = parse_step_file(step)
        assert len(result.subtasks) == 3
        assert result.subtasks[0]["marker"] == "[ ]"
        assert result.subtasks[0]["description"] == "Create user endpoint"
        assert result.subtasks[1]["marker"] == "[x]"
        assert result.subtasks[2]["marker"] == "[~]"
        assert "REST API" in result.context
        assert "FastAPI" in result.implementation_notes
        assert "Rate limiting" in result.findings

    def test_empty_step_file(self, tmp_path):
        step = tmp_path / "empty.md"
        step.write_text("# Empty Step\n\nNothing here.\n")
        result = parse_step_file(step)
        assert result.subtasks == []
        assert result.context == ""
        assert result.findings == ""

    def test_nonexistent_file(self, tmp_path):
        result = parse_step_file(tmp_path / "nope.md")
        assert result.subtasks == []


# ============ update_marker ============


class TestUpdateMarker:
    def test_mark_complete(self, tmp_path):
        f = tmp_path / "plan.md"
        f.write_text("- [ ] Setup database\n- [ ] Create API\n")
        ok = update_marker(f, "Setup database", "[x]")
        assert ok is True
        content = f.read_text()
        assert "[x] Setup database" in content
        assert "[ ] Create API" in content  # unchanged

    def test_mark_in_progress(self, tmp_path):
        f = tmp_path / "step.md"
        f.write_text("- [ ] Create user model\n")
        ok = update_marker(f, "Create user model", "[~]")
        assert ok is True
        assert "[~] Create user model" in f.read_text()

    def test_no_match(self, tmp_path):
        f = tmp_path / "plan.md"
        f.write_text("- [ ] Setup\n")
        ok = update_marker(f, "Nonexistent item", "[x]")
        assert ok is False
        assert "[ ] Setup" in f.read_text()

    def test_nonexistent_file(self, tmp_path):
        ok = update_marker(tmp_path / "nope.md", "anything", "[x]")
        assert ok is False

    def test_partial_match(self, tmp_path):
        f = tmp_path / "plan.md"
        f.write_text("- [ ] [Setup Database](./01-setup.md) — 2h est\n")
        ok = update_marker(f, "Setup Database", "[x]")
        assert ok is True
        assert "[x]" in f.read_text()


# ============ append_findings ============


class TestAppendFindings:
    def test_create_findings_section(self, tmp_path):
        f = tmp_path / "step.md"
        f.write_text("# Step 1\n\nSome content.\n")
        append_findings(f, "- [GOTCHA] Found something unexpected")
        content = f.read_text()
        assert "## Findings" in content
        assert "[GOTCHA] Found something unexpected" in content

    def test_append_to_existing(self, tmp_path):
        f = tmp_path / "step.md"
        f.write_text("# Step 1\n\n## Findings\n\n- [DECISION] Used pattern X\n")
        append_findings(f, "- [REUSE] Pattern Y works great")
        content = f.read_text()
        assert "[DECISION] Used pattern X" in content
        assert "[REUSE] Pattern Y works great" in content

    def test_nonexistent_file(self, tmp_path):
        # Should not crash
        append_findings(tmp_path / "nope.md", "anything")

    def test_append_with_following_section(self, tmp_path):
        f = tmp_path / "step.md"
        f.write_text(
            "# Step\n\n"
            "## Findings\n\n"
            "- Existing finding\n\n"
            "## Next Section\n\n"
            "Other content.\n"
        )
        append_findings(f, "- New finding")
        content = f.read_text()
        assert "- Existing finding" in content
        assert "- New finding" in content
        assert "## Next Section" in content


# ============ load_context_files ============


class TestLoadContextFiles:
    def test_root_level_step(self, tmp_path):
        proto = tmp_path / "protocol"
        ctx = proto / "_context"
        ctx.mkdir(parents=True)
        (ctx / "decisions.md").write_text("# Decisions\nUse REST.")
        (ctx / "scope.md").write_text("# Scope\nBackend only.")

        result = load_context_files(proto, "01-setup.md")
        assert "Decisions" in result
        assert "Scope" in result

    def test_grouped_step(self, tmp_path):
        proto = tmp_path / "protocol"
        group_ctx = proto / "02-infra" / "_context"
        group_ctx.mkdir(parents=True)
        (group_ctx / "infra-notes.md").write_text("# Infra\nUse PostgreSQL.")

        proto_ctx = proto / "_context"
        proto_ctx.mkdir(parents=True)
        (proto_ctx / "global.md").write_text("# Global\nProject-wide context.")

        result = load_context_files(proto, "02-infra/01-database.md")
        assert "PostgreSQL" in result
        assert "Project-wide" in result

    def test_no_context_dirs(self, tmp_path):
        proto = tmp_path / "protocol"
        proto.mkdir()
        result = load_context_files(proto, "01-setup.md")
        assert result == ""

    def test_empty_context_dir(self, tmp_path):
        proto = tmp_path / "protocol"
        (proto / "_context").mkdir(parents=True)
        result = load_context_files(proto, "01-setup.md")
        assert result == ""

    def test_non_md_files_excluded(self, tmp_path):
        proto = tmp_path / "protocol"
        ctx = proto / "_context"
        ctx.mkdir(parents=True)
        (ctx / "notes.md").write_text("# Notes")
        (ctx / "data.json").write_text("{}")
        (ctx / ".hidden").write_text("hidden")

        result = load_context_files(proto, "01-setup.md")
        assert "Notes" in result
        assert "{}" not in result


# ============ CLI interface ============


def _run_helpers(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=cwd,
    )


class TestHelpersCLI:
    def test_parse_protocol(self, tmp_path):
        proto = tmp_path / "my-proto"
        proto.mkdir()
        (proto / "plan.md").write_text(
            "# Plan\n\n"
            "- [ ] [Step 1](./01-step.md)\n"
            "- [x] [Step 2](./02-step.md)\n"
        )
        result = _run_helpers("parse-protocol", str(proto), cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert len(data["steps"]) == 2
        assert len(data["pending_steps"]) == 1
        assert data["pending_steps"][0]["marker"] == "[ ]"

    def test_update_marker_cli(self, tmp_path):
        f = tmp_path / "plan.md"
        f.write_text("- [ ] Setup\n")
        result = _run_helpers("update-marker", str(f), "Setup", "[x]", cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["updated"] is True
        assert "[x] Setup" in f.read_text()

    def test_append_findings_cli(self, tmp_path):
        f = tmp_path / "step.md"
        f.write_text("# Step\n")
        result = _run_helpers("append-findings", str(f), "- Found a bug", cwd=tmp_path)
        assert result.returncode == 0
        assert "## Findings" in f.read_text()

    def test_load_context_cli(self, tmp_path):
        proto = tmp_path / "proto"
        ctx = proto / "_context"
        ctx.mkdir(parents=True)
        (ctx / "notes.md").write_text("# Notes\nSome context.")
        (proto / "01-step.md").write_text("# Step 1")

        result = _run_helpers("load-context", str(proto), "01-step.md", cwd=tmp_path)
        assert result.returncode == 0
        assert "Notes" in result.stdout
