"""Tests for protocol v2 helpers (frontmatter, markers, step discovery, findings)."""

import json
from pathlib import Path
from unittest.mock import MagicMock  # used in TestCheckPrereqs


# Load helpers module by exec (same pattern as test_workflow_definitions.py)
HELPERS_PATH = Path(__file__).resolve().parent.parent / "static" / "workflows" / "process-protocol" / "helpers.py"
MERGE_HELPERS_PATH = Path(__file__).resolve().parent.parent / "static" / "workflows" / "merge-protocol" / "helpers.py"

_helpers_ns: dict = {"__name__": "helpers", "__file__": str(HELPERS_PATH), "__annotations__": {}}
exec(compile(HELPERS_PATH.read_text(), str(HELPERS_PATH), "exec"), _helpers_ns)

_merge_ns: dict = {"__name__": "merge_helpers", "__annotations__": {}}
exec(compile(MERGE_HELPERS_PATH.read_text(), str(MERGE_HELPERS_PATH), "exec"), _merge_ns)

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
parse_units_from_tasks = _helpers_ns["parse_units_from_tasks"]
resolve_worktree_protocol_dir = _helpers_ns["resolve_worktree_protocol_dir"]
mark_plan_in_progress = _helpers_ns["mark_plan_in_progress"]


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


# ============ Edge Cases ============


class TestEdgeCases:
    def test_discover_steps_empty_protocol_dir(self, tmp_path):
        """An empty protocol directory should return no steps."""
        proto = tmp_path / "protocol"
        proto.mkdir()
        (proto / "plan.md").write_text("# Plan\n\n## Progress\n")
        result = discover_steps(proto)
        assert result["all_steps"] == []
        assert result["pending_steps"] == []

    def test_record_findings_no_markers(self, tmp_path):
        """record_findings should not crash when step has no <!-- findings --> markers."""
        f = tmp_path / "step.md"
        f.write_text(
            "---\nid: 01\nstatus: pending\n---\n# Step\n\nNo findings section here.\n"
        )
        findings = json.dumps([{"tag": "DECISION", "text": "Use REST"}])
        # Should not raise; findings simply cannot be inserted
        record_findings(f, findings)
        text = f.read_text()
        # The file should remain unchanged (no markers to insert into)
        assert "<!-- findings -->" not in text


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


# ============ Parse Units From Tasks ============


class TestParseUnitsFromTasks:
    def test_basic_checklist(self):
        text = "- [ ] Add login endpoint\n- [ ] Add logout endpoint"
        units = parse_units_from_tasks(text)
        assert len(units) == 2
        assert units[0]["id"] == "t1"
        assert units[0]["description"] == "Add login endpoint"
        assert units[1]["id"] == "t2"
        assert units[1]["description"] == "Add logout endpoint"
        # PlanTask-shaped fields
        assert units[0]["files"] == []
        assert units[0]["test_files"] == []
        assert units[0]["depends_on"] == []

    def test_mixed_markers(self):
        text = "- [x] Already done\n- [~] In progress\n- [ ] Pending"
        units = parse_units_from_tasks(text)
        assert len(units) == 3
        assert units[0]["description"] == "Already done"
        assert units[1]["description"] == "In progress"
        assert units[2]["description"] == "Pending"

    def test_empty_input(self):
        assert parse_units_from_tasks("") == []
        assert parse_units_from_tasks("  \n  ") == []

    def test_id_stripping(self):
        text = "- [ ] Add auth middleware <!-- id:step-01 -->\n- [ ] Add routes <!-- id:step-02 -->"
        units = parse_units_from_tasks(text)
        assert units[0]["description"] == "Add auth middleware"
        assert units[1]["description"] == "Add routes"

    def test_indented_items(self):
        text = "  - [ ] Indented task\n    - [ ] More indented"
        units = parse_units_from_tasks(text)
        assert len(units) == 2
        assert units[0]["description"] == "Indented task"
        assert units[1]["description"] == "More indented"

    def test_non_checklist_lines_skipped(self):
        text = "Some preamble\n- [ ] Real task\n- Not a checklist\n\n- [ ] Another task"
        units = parse_units_from_tasks(text)
        assert len(units) == 2

    def test_prepare_step_no_headings_single_unit(self, tmp_path):
        """Tasks without ### headings → single unit with all checkboxes."""
        proto = tmp_path / "protocol"
        proto.mkdir()
        step = proto / "01-auth.md"
        step.write_text(
            "---\nid: 01-auth\nstatus: pending\n---\n"
            "# Auth\n\n"
            "## Objective\n\n<!-- objective -->\nAdd auth.\n<!-- /objective -->\n\n"
            "## Tasks\n\n<!-- tasks -->\n- [ ] Add login\n- [ ] Add logout\n<!-- /tasks -->\n\n"
            "## Findings\n\n<!-- findings -->\n<!-- /findings -->\n"
        )
        result = prepare_step(proto, "01-auth.md")
        assert "units" in result
        assert len(result["units"]) == 1
        assert "Add login" in result["units"][0]["description"]
        assert "Add logout" in result["units"][0]["description"]

    def test_prepare_step_groups_by_headings(self, tmp_path):
        """Tasks with ### headings → one unit per heading group."""
        proto = tmp_path / "protocol"
        proto.mkdir()
        step = proto / "02-refactor.md"
        step.write_text(
            "---\nid: 02-refactor\nstatus: pending\n---\n"
            "# Refactor\n\n"
            "## Objective\n\n<!-- objective -->\nClean up.\n<!-- /objective -->\n\n"
            "## Tasks\n\n<!-- tasks -->\n### Extract utils\n- [ ] Move helpers\n- [ ] Update paths\n"
            "### Update imports\n- [ ] Fix refs\n<!-- /tasks -->\n\n"
            "## Findings\n\n<!-- findings -->\n<!-- /findings -->\n"
        )
        result = prepare_step(proto, "02-refactor.md")
        assert len(result["units"]) == 2
        assert "### Extract utils" in result["units"][0]["description"]
        assert "Move helpers" in result["units"][0]["description"]
        assert "### Update imports" in result["units"][1]["description"]
        assert "Fix refs" in result["units"][1]["description"]


# ============ Worktree Path Helpers ============


class TestResolveWorktreeProtocolDir:
    """Tests for resolve_worktree_protocol_dir."""

    def test_relative_protocol_dir(self, tmp_path, monkeypatch):
        """Relative protocol_dir joined with worktree_path."""
        monkeypatch.chdir(tmp_path)
        result = resolve_worktree_protocol_dir(
            ".protocols/0001-feature",
            ".worktrees/protocol-0001",
        )
        expected = str((tmp_path / ".worktrees/protocol-0001/.protocols/0001-feature").resolve())
        assert result == expected

    def test_absolute_protocol_dir(self, tmp_path, monkeypatch):
        """Absolute protocol_dir made relative to cwd, then joined."""
        monkeypatch.chdir(tmp_path)
        abs_proto = tmp_path / ".protocols" / "0001-feature"
        result = resolve_worktree_protocol_dir(
            str(abs_proto),
            ".worktrees/protocol-0001",
        )
        expected = str((tmp_path / ".worktrees/protocol-0001/.protocols/0001-feature").resolve())
        assert result == expected

    def test_absolute_outside_cwd_raises(self, tmp_path, monkeypatch):
        """Absolute protocol_dir outside cwd raises ValueError."""
        monkeypatch.chdir(tmp_path)
        import pytest
        with pytest.raises(ValueError):
            resolve_worktree_protocol_dir(
                "/some/other/project/.protocols/001",
                ".worktrees/protocol-001",
            )


class TestMarkPlanInProgress:
    """Tests for mark_plan_in_progress."""

    def test_sets_status(self, tmp_path):
        """Sets plan.md frontmatter status to 'In Progress', preserving body."""
        plan = tmp_path / "plan.md"
        plan.write_text("---\nstatus: Draft\n---\n# Plan\n\n- [ ] Step 1\n")
        result = mark_plan_in_progress(tmp_path)
        assert result["plan_path"] == str(plan)
        fm, body = read_frontmatter(plan)
        assert fm["status"] == "In Progress"
        assert "- [ ] Step 1" in body

    def test_already_in_progress(self, tmp_path):
        """Skips if already in progress."""
        plan = tmp_path / "plan.md"
        plan.write_text("---\nstatus: In Progress\n---\n# Plan\n")
        result = mark_plan_in_progress(tmp_path)
        assert result["skipped"] is True

    def test_no_plan(self, tmp_path):
        """Returns skipped if plan.md missing."""
        result = mark_plan_in_progress(tmp_path)
        assert result["skipped"] is True


class TestUpdateStatusInWorktree:
    """Verify update_status works with step files in worktree-like paths."""

    def test_worktree_nested_path(self, tmp_path):
        """update_status finds plan.md by walking up from nested worktree path."""
        # Simulate worktree with protocol dir
        wt_proto = tmp_path / ".worktrees" / "protocol-01" / ".protocols" / "01-feature"
        wt_proto.mkdir(parents=True)

        plan = wt_proto / "plan.md"
        plan.write_text(
            "---\nstatus: In Progress\n---\n# Plan\n\n"
            "- [ ] [Step 1](./01-step.md) <!-- id:01-step -->\n"
        )

        step = wt_proto / "01-step.md"
        step.write_text("---\nid: 01-step\nstatus: pending\n---\n# Step 1\n")

        update_status(step, "done")

        # Step frontmatter updated
        fm, _ = read_frontmatter(step)
        assert fm["status"] == "done"

        # Plan marker synced
        plan_text = plan.read_text()
        assert "[x]" in plan_text


# ============ Merge-Protocol check_prereqs ============


class TestCheckPrereqs:
    """Tests for merge-protocol check_prereqs reading plan.md from worktree."""

    def _setup_worktree(self, tmp_path, plan_text, *, proto_rel=".protocols/01-feature"):
        """Create a worktree directory structure with plan.md."""
        proto_dir = tmp_path / proto_rel
        proto_dir.mkdir(parents=True)

        # Derive worktree path the same way check_prereqs does
        dir_name = proto_dir.resolve().name
        import re
        num_match = re.match(r"(\d+)", dir_name)
        protocol_num = num_match.group(1) if num_match else dir_name
        branch = f"protocol-{protocol_num}"
        wt_path = tmp_path / ".worktrees" / branch
        wt_proto = wt_path / proto_rel
        wt_proto.mkdir(parents=True)

        plan = wt_proto / "plan.md"
        plan.write_text(plan_text, encoding="utf-8")

        return proto_dir, wt_path

    def test_happy_path_all_complete(self, tmp_path, monkeypatch):
        """check_prereqs passes when all markers are [x] in worktree plan.md."""
        proto_dir, _wt = self._setup_worktree(
            tmp_path,
            "---\nstatus: In Progress\n---\n# Plan\n\n"
            "- [x] Step 1 <!-- id:s1 -->\n"
            "- [x] Step 2 <!-- id:s2 -->\n",
        )
        monkeypatch.chdir(tmp_path)

        # Mock _run to handle git status (clean) and git diff
        old_run = _merge_ns["_run"]
        def mock_run(cmd, cwd="."):
            if cmd[:2] == ["git", "status"]:
                return MagicMock(stdout="", returncode=0)
            if cmd[:2] == ["git", "diff"]:
                return MagicMock(stdout="file.py | 5 ++---\n 1 file changed\n", returncode=0)
            return old_run(cmd, cwd=cwd)

        _merge_ns["_run"] = mock_run
        try:
            import io, sys
            captured = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured
            try:
                _merge_ns["check_prereqs"](str(proto_dir))
            finally:
                sys.stdout = old_stdout
            result = json.loads(captured.getvalue())
            assert result["branch"] == "protocol-01"
            assert result["step_count"] == 2
        finally:
            _merge_ns["_run"] = old_run

    def test_incomplete_markers_fails(self, tmp_path, monkeypatch):
        """check_prereqs exits with error when markers are incomplete."""
        proto_dir, _wt = self._setup_worktree(
            tmp_path,
            "---\nstatus: In Progress\n---\n# Plan\n\n"
            "- [x] Step 1 <!-- id:s1 -->\n"
            "- [ ] Step 2 <!-- id:s2 -->\n",
        )
        monkeypatch.chdir(tmp_path)

        import io, sys
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            with __import__("pytest").raises(SystemExit):
                _merge_ns["check_prereqs"](str(proto_dir))
        finally:
            sys.stdout = old_stdout
        output = captured.getvalue()
        assert "not complete" in output

    def test_worktree_not_found_fails(self, tmp_path, monkeypatch):
        """check_prereqs exits with error when worktree doesn't exist."""
        proto_dir = tmp_path / ".protocols" / "01-feature"
        proto_dir.mkdir(parents=True)
        monkeypatch.chdir(tmp_path)

        import io, sys
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            with __import__("pytest").raises(SystemExit):
                _merge_ns["check_prereqs"](str(proto_dir))
        finally:
            sys.stdout = old_stdout
        output = captured.getvalue()
        assert "Worktree not found" in output

    def test_non_numeric_protocol_dir(self, tmp_path, monkeypatch):
        """check_prereqs handles non-numeric directory name (fallback to full name)."""
        proto_dir, _wt = self._setup_worktree(
            tmp_path,
            "---\nstatus: In Progress\n---\n# Plan\n\n"
            "- [x] Step 1 <!-- id:s1 -->\n",
            proto_rel=".protocols/my-feature",
        )
        monkeypatch.chdir(tmp_path)

        old_run = _merge_ns["_run"]
        def mock_run(cmd, cwd="."):
            if cmd[:2] == ["git", "status"]:
                return MagicMock(stdout="", returncode=0)
            if cmd[:2] == ["git", "diff"]:
                return MagicMock(stdout="", returncode=0)
            return old_run(cmd, cwd=cwd)

        _merge_ns["_run"] = mock_run
        try:
            import io, sys
            captured = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured
            try:
                _merge_ns["check_prereqs"](str(proto_dir))
            finally:
                sys.stdout = old_stdout
            result = json.loads(captured.getvalue())
            # Non-numeric: branch uses full dir name
            assert result["branch"] == "protocol-my-feature"
            assert result["protocol_name"] == "my-feature"
        finally:
            _merge_ns["_run"] = old_run

    def test_plan_missing_in_worktree_fails(self, tmp_path, monkeypatch):
        """check_prereqs fails when worktree exists but plan.md is missing inside it."""
        proto_dir = tmp_path / ".protocols" / "01-feature"
        proto_dir.mkdir(parents=True)

        # Create worktree dir WITHOUT plan.md inside protocol subdir
        wt_path = tmp_path / ".worktrees" / "protocol-01"
        wt_proto = wt_path / ".protocols" / "01-feature"
        wt_proto.mkdir(parents=True)
        # No plan.md written

        monkeypatch.chdir(tmp_path)

        import io, sys
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            with __import__("pytest").raises(SystemExit):
                _merge_ns["check_prereqs"](str(proto_dir))
        finally:
            sys.stdout = old_stdout
        output = captured.getvalue()
        assert "plan.md not found" in output
