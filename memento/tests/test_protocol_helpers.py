"""Tests for protocol v2 helpers (frontmatter, markers, step discovery, findings)."""

import json
from pathlib import Path

import pytest

# Load helpers module by exec (same pattern as test_workflow_definitions.py)
HELPERS_PATH = Path(__file__).resolve().parent.parent / "static" / "workflows" / "process-protocol" / "helpers.py"

_helpers_ns: dict = {"__name__": "helpers", "__annotations__": {}}
exec(compile(HELPERS_PATH.read_text(), str(HELPERS_PATH), "exec"), _helpers_ns)

read_frontmatter = _helpers_ns["read_frontmatter"]
write_frontmatter = _helpers_ns["write_frontmatter"]
extract_between_markers = _helpers_ns["extract_between_markers"]
replace_between_markers = _helpers_ns["replace_between_markers"]
discover_steps = _helpers_ns["discover_steps"]
render_task_full = _helpers_ns["render_task_full"]
render_task_compact = _helpers_ns["render_task_compact"]
prepare_step = _helpers_ns["prepare_step"]
record_findings = _helpers_ns["record_findings"]
update_status = _helpers_ns["update_status"]
update_marker = _helpers_ns["update_marker"]
migrate_protocol = _helpers_ns["migrate_protocol"]


# ============ Frontmatter ============


class TestFrontmatter:
    def test_read_frontmatter(self, tmp_path):
        f = tmp_path / "step.md"
        f.write_text("---\nid: 01-setup\nstatus: pending\n---\n# Setup\n\nBody here.\n")
        fm, body = read_frontmatter(f)
        assert fm["id"] == "01-setup"
        assert fm["status"] == "pending"
        assert body.startswith("# Setup")

    def test_read_frontmatter_no_frontmatter(self, tmp_path):
        f = tmp_path / "step.md"
        f.write_text("# No frontmatter\n\nBody.\n")
        fm, body = read_frontmatter(f)
        assert fm == {}
        assert "No frontmatter" in body

    def test_write_frontmatter(self, tmp_path):
        f = tmp_path / "step.md"
        f.write_text("")  # Create empty file
        write_frontmatter(f, {"id": "02-db", "status": "done"}, "# Database\n")
        fm, body = read_frontmatter(f)
        assert fm["id"] == "02-db"
        assert fm["status"] == "done"
        assert "Database" in body


# ============ Markers ============


class TestMarkers:
    def test_extract_between_markers(self):
        text = "before\n<!-- tasks -->\n- [ ] Do thing\n- [ ] Other\n<!-- /tasks -->\nafter"
        result = extract_between_markers(text, "tasks")
        assert "- [ ] Do thing" in result
        assert "- [ ] Other" in result

    def test_extract_missing_marker(self):
        assert extract_between_markers("no markers here", "tasks") is None

    def test_replace_between_markers(self):
        text = "<!-- findings -->\nold stuff\n<!-- /findings -->"
        result = replace_between_markers(text, "findings", "- [DECISION] new finding")
        assert "new finding" in result
        assert "old stuff" not in result


# ============ Step Discovery ============


class TestDiscoverSteps:
    def _make_protocol(self, tmp_path):
        """Create a test protocol directory with frontmatter step files."""
        proto = tmp_path / "protocol"
        proto.mkdir()

        # plan.md with id markers
        (proto / "plan.md").write_text(
            "# Plan\n\n## Progress\n"
            "- [ ] [Setup](./01-setup.md) <!-- id:01-setup --> — 2h\n"
            "- [ ] [Database](./02-database.md) <!-- id:02-database --> — 3h\n"
        )

        # Step files
        (proto / "01-setup.md").write_text(
            "---\nid: 01-setup\nstatus: pending\n---\n# Setup\n\n"
            "## Tasks\n\n<!-- tasks -->\n- [ ] Init project\n<!-- /tasks -->\n\n"
            "## Findings\n\n<!-- findings -->\n<!-- /findings -->\n"
        )
        (proto / "02-database.md").write_text(
            "---\nid: 02-database\nstatus: done\n---\n# Database\n"
        )
        return proto

    def test_discover_steps_returns_all_and_pending(self, tmp_path):
        proto = self._make_protocol(tmp_path)
        result = discover_steps(proto)
        assert len(result["all_steps"]) == 2
        assert len(result["pending_steps"]) == 1
        assert result["pending_steps"][0]["id"] == "01-setup"

    def test_discover_steps_orders_by_plan_progress_ids(self, tmp_path):
        proto = self._make_protocol(tmp_path)
        result = discover_steps(proto)
        ids = [s["id"] for s in result["all_steps"]]
        assert ids == ["01-setup", "02-database"]

    def test_discover_steps_orders_by_plan_progress_ids_then_fallback(self, tmp_path):
        proto = self._make_protocol(tmp_path)
        # Add a step not in plan.md
        (proto / "03-extra.md").write_text(
            "---\nid: 03-extra\nstatus: pending\n---\n# Extra\n"
        )
        result = discover_steps(proto)
        ids = [s["id"] for s in result["all_steps"]]
        assert ids[0] == "01-setup"
        assert ids[1] == "02-database"
        assert "03-extra" in ids


# ============ Task Rendering ============


class TestRenderTask:
    def _make_step(self, tmp_path):
        f = tmp_path / "step.md"
        f.write_text(
            "---\nid: 01-auth\nstatus: pending\n---\n"
            "# Auth\n\n"
            "## Objective\n\n<!-- objective -->\nImplement OAuth2 flow.\n<!-- /objective -->\n\n"
            "## Tasks\n\n<!-- tasks -->\n- [ ] Add middleware\n- [ ] Add routes\n<!-- /tasks -->\n\n"
            "## Constraints\n\n<!-- constraints -->\n- Must use existing session store\n<!-- /constraints -->\n\n"
            "## Verification\n\n<!-- verification -->\n```bash\npytest tests/test_auth.py\n```\n<!-- /verification -->\n\n"
            "## Context\n\n<!-- context:inline -->\nUses PKCE flow.\n<!-- /context:inline -->\n\n"
            "<!-- context:files -->\n- .memory_bank/patterns/api-design.md\n- .protocols/001/_context/auth-research.md\n<!-- /context:files -->\n\n"
            "## Starting Points\n\n<!-- starting_points -->\n- backend/auth/middleware.py\n<!-- /starting_points -->\n\n"
            "## Findings\n\n<!-- findings -->\n<!-- /findings -->\n"
        )
        return f

    def test_render_task_full(self, tmp_path):
        f = self._make_step(tmp_path)
        result = render_task_full(f)
        assert "## Objective" in result
        assert "OAuth2" in result
        assert "## Tasks" in result
        assert "Add middleware" in result
        assert "## Constraints" in result
        assert "## Verification" in result
        assert "pytest tests/test_auth.py" in result
        assert "## Context" in result
        assert "PKCE" in result
        assert "## Starting Points" in result

    def test_render_task_compact(self, tmp_path):
        f = self._make_step(tmp_path)
        result = render_task_compact(f)
        assert "## Objective" in result
        assert "## Tasks" in result
        assert "## Constraints" in result
        # Compact should NOT have verification or inline context
        assert "Verification" not in result
        assert "PKCE" not in result

    def test_render_falls_back_to_heading(self, tmp_path):
        """Falls back to ## heading when markers are missing."""
        f = tmp_path / "step.md"
        f.write_text(
            "---\nid: 01-test\nstatus: pending\n---\n"
            "# Test Step\n\n"
            "## Objective\n\nDo something.\n\n"
            "## Tasks\n\n- [ ] Task 1\n"
        )
        result = render_task_full(f)
        assert "Do something" in result
        assert "Task 1" in result


# ============ Prepare Step ============


class TestPrepareStep:
    def test_prepare_step(self, tmp_path):
        proto = tmp_path / "protocol"
        proto.mkdir()
        step = proto / "01-auth.md"
        step.write_text(
            "---\nid: 01-auth\nstatus: pending\n---\n"
            "# Auth\n\n"
            "## Objective\n\n<!-- objective -->\nAdd auth.\n<!-- /objective -->\n\n"
            "## Tasks\n\n<!-- tasks -->\n- [ ] Add login\n<!-- /tasks -->\n\n"
            "## Verification\n\n<!-- verification -->\n```bash\npytest tests/\n```\n<!-- /verification -->\n\n"
            "<!-- context:files -->\n- .memory_bank/patterns/api-design.md\n- .protocols/_context/arch.md\n<!-- /context:files -->\n\n"
            "<!-- starting_points -->\n- backend/auth.py\n<!-- /starting_points -->\n\n"
            "## Findings\n\n<!-- findings -->\n<!-- /findings -->\n"
        )
        result = prepare_step(proto, "01-auth.md")
        assert result["id"] == "01-auth"
        assert "Add auth" in result["task_full_md"]
        assert "Add login" in result["task_compact_md"]
        assert ".memory_bank/patterns/api-design.md" in result["mb_refs"]
        assert ".protocols/_context/arch.md" in result["context_files"]
        assert "backend/auth.py" in result["starting_points"]
        assert "pytest tests/" in result["verification_commands"]


# ============ Findings ============


class TestRecordFindings:
    def test_record_findings_appends_and_dedupes(self, tmp_path):
        f = tmp_path / "step.md"
        f.write_text(
            "---\nid: 01\nstatus: pending\n---\n# Step\n\n"
            "## Findings\n\n<!-- findings -->\n- [DECISION] Use REST\n<!-- /findings -->\n"
        )
        # Append with one duplicate and one new
        findings = json.dumps([
            {"tag": "DECISION", "text": "Use REST"},  # duplicate
            {"tag": "GOTCHA", "text": "Rate limit on API"},  # new
        ])
        record_findings(f, findings)
        text = f.read_text()
        assert text.count("Use REST") == 1  # deduped
        assert "Rate limit on API" in text

    def test_record_findings_preserving_existing_lines(self, tmp_path):
        f = tmp_path / "step.md"
        f.write_text(
            "---\nid: 01\nstatus: pending\n---\n# Step\n\n"
            "## Findings\n\n<!-- findings -->\n- Manual note here\n<!-- /findings -->\n"
        )
        findings = json.dumps([{"tag": "REUSE", "text": "Pattern X"}])
        record_findings(f, findings)
        text = f.read_text()
        assert "Manual note here" in text
        assert "Pattern X" in text

    def test_record_findings_from_develop_result(self, tmp_path):
        f = tmp_path / "step.md"
        f.write_text(
            "---\nid: 01\nstatus: pending\n---\n# Step\n\n"
            "## Findings\n\n<!-- findings -->\n<!-- /findings -->\n"
        )
        # DevelopResult-style JSON
        result_json = json.dumps({
            "summary": "Done",
            "files_changed": ["a.py"],
            "findings": [{"tag": "DECISION", "text": "Used adapter pattern"}],
        })
        record_findings(f, result_json)
        text = f.read_text()
        assert "adapter pattern" in text


# ============ Status ============


class TestUpdateStatus:
    def test_update_status_and_plan_sync(self, tmp_path):
        proto = tmp_path / "protocol"
        proto.mkdir()

        step = proto / "01-setup.md"
        step.write_text("---\nid: 01-setup\nstatus: pending\n---\n# Setup\n")

        plan = proto / "plan.md"
        plan.write_text(
            "# Plan\n\n## Progress\n"
            "- [ ] [Setup](./01-setup.md) <!-- id:01-setup --> — 2h\n"
        )

        update_status(step, "done")

        # Check frontmatter updated
        fm, _ = read_frontmatter(step)
        assert fm["status"] == "done"

        # Check plan.md marker updated
        plan_text = plan.read_text()
        assert "[x]" in plan_text
        assert "[ ]" not in plan_text


# ============ Update Marker ============


class TestUpdateMarker:
    def test_update_marker_by_id(self, tmp_path):
        f = tmp_path / "plan.md"
        f.write_text(
            "## Progress\n"
            "- [ ] [Setup](./01-setup.md) <!-- id:01-setup --> — 2h\n"
            "- [ ] [Database](./02-db.md) <!-- id:02-db --> — 3h\n"
        )
        ok = update_marker(f, "02-db", "[x]")
        assert ok
        text = f.read_text()
        assert "[x] [Database]" in text
        assert "[ ] [Setup]" in text  # unchanged


# ============ Migration ============


class TestMigration:
    def test_migrate_adds_frontmatter_and_markers(self, tmp_path):
        proto = tmp_path / "protocol"
        proto.mkdir()

        (proto / "plan.md").write_text(
            "## Progress\n- [ ] [Setup](./01-setup.md) — 2h\n"
        )
        (proto / "01-setup.md").write_text(
            "# Setup\n\n## Objective\n\nDo setup.\n\n"
            "## Tasks\n\n- [ ] Init\n- [ ] Config\n"
        )

        result = migrate_protocol(proto)
        assert "01-setup.md" in result["migrated"]

        # Check frontmatter added
        fm, body = read_frontmatter(proto / "01-setup.md")
        assert fm["id"] == "01-setup"
        assert fm["status"] == "pending"

        # Check markers added
        assert "<!-- tasks -->" in body
        assert "<!-- findings -->" in body

        # Check plan.md got id markers
        plan_text = (proto / "plan.md").read_text()
        assert "<!-- id:" in plan_text
