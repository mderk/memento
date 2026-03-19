"""Tests for workflow engine helpers (protocol v2 parsing utilities).

Tests the CLI interface and core functions of helpers.py.
Detailed unit tests for each function are in test_protocol_helpers.py.
"""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "static"
    / "workflows"
    / "process-protocol"
    / "helpers.py"
)

# Load functions directly for unit tests
_code = SCRIPT.read_text()
_ns: dict = {"__file__": str(SCRIPT)}
exec(compile(_code, str(SCRIPT), "exec"), _ns)

read_frontmatter = _ns["read_frontmatter"]
write_frontmatter = _ns["write_frontmatter"]
extract_between_markers = _ns["extract_between_markers"]
replace_between_markers = _ns["replace_between_markers"]
discover_steps = _ns["discover_steps"]
update_marker = _ns["update_marker"]
update_status = _ns["update_status"]
load_context_files = _ns["load_context_files"]
record_findings = _ns["record_findings"]


# NOTE: TestUpdateMarker is not duplicated here. The canonical tests for
# update_marker live in test_protocol_helpers.py (TestUpdateMarker class).


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
    def test_discover_steps_cli(self, tmp_path):
        proto = tmp_path / "my-proto"
        proto.mkdir()
        (proto / "plan.md").write_text(
            "# Plan\n\n"
            "- [ ] [Step 1](./01-step.md) <!-- id:01-step -->\n"
            "- [x] [Step 2](./02-step.md) <!-- id:02-step -->\n"
        )
        (proto / "01-step.md").write_text("---\nid: 01-step\nstatus: pending\n---\n# Step 1\n")
        (proto / "02-step.md").write_text("---\nid: 02-step\nstatus: done\n---\n# Step 2\n")

        result = _run_helpers("discover-steps", str(proto), cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert len(data["all_steps"]) == 2
        assert len(data["pending_steps"]) == 1

    def test_update_marker_cli(self, tmp_path):
        f = tmp_path / "plan.md"
        f.write_text("- [ ] [Setup](./01.md) <!-- id:01 -->\n")
        result = _run_helpers("update-marker", str(f), "01", "[x]", cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["updated"] is True
        assert "[x] [Setup]" in f.read_text()

    def test_record_findings_cli(self, tmp_path):
        f = tmp_path / "step.md"
        f.write_text(
            "---\nid: 01\nstatus: pending\n---\n# Step\n\n"
            "## Findings\n\n<!-- findings -->\n<!-- /findings -->\n"
        )
        findings = json.dumps([{"tag": "DECISION", "text": "Use REST"}])
        result = _run_helpers("record-findings", str(f), findings, cwd=tmp_path)
        assert result.returncode == 0
        assert "REST" in f.read_text()

    def test_load_context_cli(self, tmp_path):
        proto = tmp_path / "proto"
        ctx = proto / "_context"
        ctx.mkdir(parents=True)
        (ctx / "notes.md").write_text("# Notes\nSome context.")
        (proto / "01-step.md").write_text("# Step 1")

        result = _run_helpers("load-context", str(proto), "01-step.md", cwd=tmp_path)
        assert result.returncode == 0
        assert "Notes" in result.stdout

    def test_update_status_cli(self, tmp_path):
        proto = tmp_path / "proto"
        proto.mkdir()
        step = proto / "01.md"
        step.write_text("---\nid: 01\nstatus: pending\n---\n# Step\n")
        (proto / "plan.md").write_text("- [ ] [Step](./01.md) <!-- id:01 -->\n")

        result = _run_helpers("update-status", str(step), "done", cwd=tmp_path)
        assert result.returncode == 0
        fm, _ = read_frontmatter(step)
        assert fm["status"] == "done"
