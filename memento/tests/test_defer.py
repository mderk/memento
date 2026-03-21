"""Tests for defer.py backlog management script."""

import importlib.util
import io
import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "static"
    / "skills"
    / "defer"
    / "scripts"
    / "defer.py"
)

# Import defer.py as a module so we can test functions directly.
_spec = importlib.util.spec_from_file_location("defer", SCRIPT)
_defer_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_defer_mod)

slugify = _defer_mod.slugify
yaml_escape = _defer_mod.yaml_escape
parse_frontmatter = _defer_mod.parse_frontmatter
ensure_backlog = _defer_mod.ensure_backlog
load_items = _defer_mod.load_items
filter_items = _defer_mod.filter_items
cmd_create = _defer_mod.cmd_create
cmd_close = _defer_mod.cmd_close
cmd_list = _defer_mod.cmd_list
cmd_view = _defer_mod.cmd_view
cmd_bootstrap = _defer_mod.cmd_bootstrap
cmd_link_finding = _defer_mod.cmd_link_finding
ITEMS_DIR = _defer_mod.ITEMS_DIR
ARCHIVE_DIR = _defer_mod.ARCHIVE_DIR
BACKLOG_DIR = _defer_mod.BACKLOG_DIR


def _run(cmd_fn, tmp_path, **kwargs):
    """Call a cmd_* function with cwd=tmp_path, capture JSON stdout."""
    args = Namespace(**kwargs)
    buf = io.StringIO()
    with patch.object(_defer_mod, "BACKLOG_DIR", tmp_path / ".backlog"), \
         patch.object(_defer_mod, "ITEMS_DIR", tmp_path / ".backlog" / "items"), \
         patch.object(_defer_mod, "ARCHIVE_DIR", tmp_path / ".backlog" / "archive"), \
         patch.object(_defer_mod, "TEMPLATES_DIR", tmp_path / ".backlog" / "templates"), \
         patch.object(_defer_mod, "VIEWS_DIR", tmp_path / ".backlog" / "views"), \
         patch("sys.stdout", buf):
        cmd_fn(args)
    output = buf.getvalue()
    if output.strip():
        return json.loads(output)
    return {}


def _create(tmp_path, title, type_="bug", priority="p1", area="", effort="",
            origin="", description=""):
    """Shorthand for creating a backlog item."""
    return _run(cmd_create, tmp_path, title=title, type=type_, priority=priority,
                area=area, effort=effort, origin=origin, description=description)


def _list(tmp_path, **filters):
    """Shorthand for listing items."""
    return _run(cmd_list, tmp_path,
                status=filters.get("status"),
                type=filters.get("type"),
                area=filters.get("area"),
                priority=filters.get("priority"),
                effort=filters.get("effort"))


def _close(tmp_path, slug):
    return _run(cmd_close, tmp_path, slug=slug)


def _bootstrap(tmp_path):
    return _run(cmd_bootstrap, tmp_path)


def _view(tmp_path, group_by, output=None, **filters):
    return _run(cmd_view, tmp_path, group_by=group_by, output=output,
                status=filters.get("status"),
                type=filters.get("type"),
                area=filters.get("area"),
                priority=filters.get("priority"),
                effort=filters.get("effort"))


def _view_raw(tmp_path, group_by, **filters):
    """Return raw stdout from view (for markdown checks)."""
    args = Namespace(group_by=group_by, output=None,
                     status=filters.get("status"),
                     type=filters.get("type"),
                     area=filters.get("area"),
                     priority=filters.get("priority"),
                     effort=filters.get("effort"))
    buf = io.StringIO()
    with patch.object(_defer_mod, "BACKLOG_DIR", tmp_path / ".backlog"), \
         patch.object(_defer_mod, "ITEMS_DIR", tmp_path / ".backlog" / "items"), \
         patch.object(_defer_mod, "ARCHIVE_DIR", tmp_path / ".backlog" / "archive"), \
         patch.object(_defer_mod, "TEMPLATES_DIR", tmp_path / ".backlog" / "templates"), \
         patch.object(_defer_mod, "VIEWS_DIR", tmp_path / ".backlog" / "views"), \
         patch("sys.stdout", buf):
        cmd_view(args)
    return buf.getvalue()


# ---- subprocess helpers for CLI contract tests ----

def run_defer(*args: str, cwd: Path) -> dict:
    """Run defer.py as subprocess, return parsed JSON output."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=cwd,
    )
    if result.returncode != 0:
        try:
            return {**json.loads(result.stderr), "_rc": result.returncode}
        except json.JSONDecodeError:
            raise AssertionError(
                f"defer.py failed (rc={result.returncode}):\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )
    return json.loads(result.stdout)


def run_defer_raw(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=cwd,
    )


# --- Bootstrap ---

class TestBootstrap:
    def test_creates_scaffolding(self, tmp_path):
        out = _bootstrap(tmp_path)
        assert out["action"] == "bootstrap"
        assert out["already_existed"] is False
        assert (tmp_path / ".backlog" / "items").is_dir()
        assert (tmp_path / ".backlog" / "archive").is_dir()
        assert (tmp_path / ".backlog" / "templates" / "item.md").exists()
        assert (tmp_path / ".backlog" / "README.md").exists()

    def test_idempotent(self, tmp_path):
        _bootstrap(tmp_path)
        out = _bootstrap(tmp_path)
        assert out["already_existed"] is True
        assert out["created"] == []


# --- Create ---

class TestCreate:
    def test_basic_create(self, tmp_path):
        out = _create(tmp_path, "Fix login bug")
        assert out["action"] == "create"
        assert out["slug"] == "fix-login-bug"
        assert out["type"] == "bug"
        assert out["priority"] == "p1"

        item = tmp_path / ".backlog" / "items" / "fix-login-bug.md"
        assert item.exists()
        content = item.read_text()
        assert "title: Fix login bug" in content
        assert "type: bug" in content
        assert "priority: p1" in content
        assert "status: open" in content

    def test_create_with_area_and_effort(self, tmp_path):
        out = _create(tmp_path, "Add caching", type_="debt", priority="p2",
                       area="api", effort="m")
        assert out["area"] == "api"
        assert out["effort"] == "m"

        content = (tmp_path / ".backlog" / "items" / "add-caching.md").read_text()
        assert "area: api" in content
        assert "effort: m" in content

    def test_create_with_description(self, tmp_path):
        out = _create(tmp_path, "Add rate limiting", type_="idea", priority="p3",
                       description="Need rate limiting on public endpoints")
        content = (tmp_path / ".backlog" / "items" / f"{out['slug']}.md").read_text()
        assert "Need rate limiting on public endpoints" in content

    def test_create_with_origin(self, tmp_path):
        out = _create(tmp_path, "SQL injection risk", type_="risk", priority="p0",
                       origin=".protocols/0005/03-api.md")
        assert out["origin"] == ".protocols/0005/03-api.md"
        content = (tmp_path / ".backlog" / "items" / f"{out['slug']}.md").read_text()
        assert ".protocols/0005/03-api.md" in content

    @pytest.mark.e2e
    def test_invalid_type(self, tmp_path):
        """CLI argparse rejects invalid type (subprocess needed for exit code)."""
        result = run_defer_raw(
            "create", "--title", "Test",
            "--type", "invalid", "--priority", "p1",
            cwd=tmp_path,
        )
        assert result.returncode != 0
        assert "invalid choice" in result.stderr

    def test_invalid_effort(self, tmp_path):
        with pytest.raises(SystemExit):
            _create(tmp_path, "Test", effort="xxl")

    def test_duplicate_slug_gets_suffix(self, tmp_path):
        _create(tmp_path, "Fix bug")
        out = _create(tmp_path, "Fix bug", type_="debt", priority="p2")
        assert out["slug"] == "fix-bug-2"
        assert (tmp_path / ".backlog" / "items" / "fix-bug.md").exists()
        assert (tmp_path / ".backlog" / "items" / "fix-bug-2.md").exists()

    def test_special_chars_in_title(self, tmp_path):
        out = _create(tmp_path, "is_admin_user() returns False — broken")
        assert out["slug"]
        assert (tmp_path / ".backlog" / "items" / f"{out['slug']}.md").exists()

    def test_non_ascii_title(self, tmp_path):
        out = _create(tmp_path, "Тестовая задача", type_="idea", priority="p3")
        assert out["slug"].startswith("item-")
        assert (tmp_path / ".backlog" / "items" / f"{out['slug']}.md").exists()

    def test_bootstraps_automatically(self, tmp_path):
        assert not (tmp_path / ".backlog").exists()
        out = _create(tmp_path, "Test")
        assert (tmp_path / ".backlog" / "items").is_dir()
        assert "bootstrapped" in out

    def test_yaml_escaping_quotes_in_title(self, tmp_path):
        import yaml
        out = _create(tmp_path, 'Fix "broken" auth')
        content = (tmp_path / ".backlog" / "items" / f"{out['slug']}.md").read_text()
        parts = content.split("---")
        assert len(parts) >= 3, f"Frontmatter missing: {content[:200]}"
        frontmatter = yaml.safe_load(parts[1])
        assert frontmatter["title"] == 'Fix "broken" auth'

    def test_yaml_escaping_colon_in_origin(self, tmp_path):
        out = _create(tmp_path, "Test", type_="debt", priority="p2",
                       origin="protocol: step-03: substep")
        content = (tmp_path / ".backlog" / "items" / f"{out['slug']}.md").read_text()
        assert "protocol" in content
        assert '"' in content.split("origin:")[1].split("\n")[0]

    def test_yaml_escaping_newline_in_title(self, tmp_path):
        out = _create(tmp_path, "Line one\nLine two")
        content = (tmp_path / ".backlog" / "items" / f"{out['slug']}.md").read_text()
        parts = content.split("---")
        assert len(parts) >= 3, f"Frontmatter broken by newline: {content[:200]}"
        title_line = [ln for ln in parts[1].splitlines() if ln.strip().startswith("title:")][0]
        assert "\\n" in title_line


# --- Close ---

class TestClose:
    def test_close_moves_to_archive(self, tmp_path):
        _create(tmp_path, "Old bug", priority="p2")
        out = _close(tmp_path, "old-bug")
        assert out["action"] == "close"
        assert not (tmp_path / ".backlog" / "items" / "old-bug.md").exists()
        archived = tmp_path / ".backlog" / "archive" / "old-bug.md"
        assert archived.exists()
        assert "status: closed" in archived.read_text()

    def test_close_nonexistent(self, tmp_path):
        _bootstrap(tmp_path)
        with pytest.raises(SystemExit):
            _close(tmp_path, "nonexistent")


# --- List ---

class TestList:
    def _seed(self, tmp_path):
        _create(tmp_path, "Bug A", area="api")
        _create(tmp_path, "Debt B", type_="debt", priority="p2", area="api", effort="s")
        _create(tmp_path, "Idea C", type_="idea", priority="p3", area="ui")

    def test_list_all(self, tmp_path):
        self._seed(tmp_path)
        out = _list(tmp_path)
        assert out["count"] == 3

    def test_list_empty(self, tmp_path):
        _bootstrap(tmp_path)
        out = _list(tmp_path)
        assert out["count"] == 0
        assert out["items"] == []

    def test_list_no_backlog_dir(self, tmp_path):
        out = _list(tmp_path)
        assert out["count"] == 0

    def test_filter_by_type(self, tmp_path):
        self._seed(tmp_path)
        out = _list(tmp_path, type="bug")
        assert out["count"] == 1
        assert out["items"][0]["title"] == "Bug A"

    def test_filter_by_area(self, tmp_path):
        self._seed(tmp_path)
        out = _list(tmp_path, area="api")
        assert out["count"] == 2

    def test_filter_by_priority(self, tmp_path):
        self._seed(tmp_path)
        out = _list(tmp_path, priority="p3")
        assert out["count"] == 1
        assert out["items"][0]["title"] == "Idea C"

    def test_filter_by_effort(self, tmp_path):
        self._seed(tmp_path)
        out = _list(tmp_path, effort="s")
        assert out["count"] == 1
        assert out["items"][0]["title"] == "Debt B"

    def test_filter_by_status(self, tmp_path):
        self._seed(tmp_path)
        _close(tmp_path, "bug-a")
        out = _list(tmp_path, status="open")
        assert out["count"] == 2

    def test_combined_filters(self, tmp_path):
        self._seed(tmp_path)
        out = _list(tmp_path, type="debt", area="api")
        assert out["count"] == 1
        assert out["items"][0]["title"] == "Debt B"

    def test_no_match(self, tmp_path):
        self._seed(tmp_path)
        out = _list(tmp_path, area="nonexistent")
        assert out["count"] == 0

    def test_list_includes_area_and_effort(self, tmp_path):
        self._seed(tmp_path)
        out = _list(tmp_path)
        item_b = next(i for i in out["items"] if i["title"] == "Debt B")
        assert item_b["area"] == "api"
        assert item_b["effort"] == "s"


# --- View ---

class TestView:
    def _seed(self, tmp_path):
        _create(tmp_path, "Critical bug", area="api", effort="s")
        _create(tmp_path, "Low debt", type_="debt", priority="p3", area="api")
        _create(tmp_path, "UI idea", type_="idea", priority="p2", area="ui")

    def test_view_to_file(self, tmp_path):
        self._seed(tmp_path)
        out_path = str(tmp_path / ".backlog" / "views" / "by-priority.md")
        out = _view(tmp_path, "priority", output=out_path)
        assert out["action"] == "view"
        assert out["items"] == 3
        assert out["groups"] == 3
        content = Path(out_path).read_text()
        assert "## p1" in content
        assert "## p2" in content
        assert "## p3" in content
        assert "Critical bug" in content

    def test_view_to_stdout(self, tmp_path):
        self._seed(tmp_path)
        output = _view_raw(tmp_path, "type")
        assert "## bug" in output
        assert "## debt" in output
        assert "## idea" in output

    def test_view_group_by_area(self, tmp_path):
        self._seed(tmp_path)
        out_path = str(tmp_path / ".backlog" / "views" / "by-area.md")
        out = _view(tmp_path, "area", output=out_path)
        assert out["groups"] == 2
        content = Path(out_path).read_text()
        assert "## api (2)" in content
        assert "## ui (1)" in content

    def test_view_with_filter(self, tmp_path):
        self._seed(tmp_path)
        out_path = str(tmp_path / ".backlog" / "views" / "filtered.md")
        out = _view(tmp_path, "type", output=out_path, area="api")
        assert out["items"] == 2
        content = Path(out_path).read_text()
        assert "(area=api)" in content
        assert "UI idea" not in content

    def test_view_excludes_group_by_column(self, tmp_path):
        self._seed(tmp_path)
        output = _view_raw(tmp_path, "priority")
        header_lines = [ln for ln in output.splitlines() if ln.startswith("| # |")]
        for h in header_lines:
            assert "Priority" not in h

    def test_view_priority_order(self, tmp_path):
        self._seed(tmp_path)
        output = _view_raw(tmp_path, "priority")
        p1_pos = output.index("## p1")
        p2_pos = output.index("## p2")
        p3_pos = output.index("## p3")
        assert p1_pos < p2_pos < p3_pos

    def test_view_contains_regen_command(self, tmp_path):
        self._seed(tmp_path)
        out_path = str(tmp_path / ".backlog" / "views" / "test.md")
        _view(tmp_path, "area", output=out_path, type="bug")
        content = Path(out_path).read_text()
        assert "Regenerate:" in content
        assert "--group-by area" in content
        assert "--type bug" in content

    def test_view_links_to_items(self, tmp_path):
        self._seed(tmp_path)
        output = _view_raw(tmp_path, "type")
        assert "../items/critical-bug.md" in output

    def test_view_empty_field_shows_none(self, tmp_path):
        _create(tmp_path, "No area")
        output = _view_raw(tmp_path, "area")
        assert "## (none)" in output


# --- Link Finding ---

class TestLinkFinding:
    def test_appends_findings_section(self, tmp_path):
        (tmp_path / ".backlog" / "items").mkdir(parents=True)
        (tmp_path / ".backlog" / "items" / "my-bug.md").write_text("---\ntitle: My Bug\n---\n")
        step = tmp_path / "step-03.md"
        step.write_text("# Step 3\n\nSome content\n")

        args = Namespace(step_file=str(step), slug="my-bug", title="My Bug Title")
        with patch.object(_defer_mod, "BACKLOG_DIR", tmp_path / ".backlog"), \
             patch.object(_defer_mod, "ITEMS_DIR", tmp_path / ".backlog" / "items"), \
             patch.object(_defer_mod, "ARCHIVE_DIR", tmp_path / ".backlog" / "archive"):
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                cmd_link_finding(args)
            out = json.loads(buf.getvalue())

        assert out["action"] == "link_finding"
        content = step.read_text()
        assert "## Findings" in content
        assert "[DEFER] My Bug Title" in content
        assert "my-bug.md" in content

    def test_inserts_into_existing_findings(self, tmp_path):
        (tmp_path / ".backlog" / "items").mkdir(parents=True)
        (tmp_path / ".backlog" / "items" / "my-bug.md").write_text("---\ntitle: My Bug\n---\n")
        step = tmp_path / "step-03.md"
        step.write_text("# Step 3\n\n## Findings\n\nExisting finding\n")

        args = Namespace(step_file=str(step), slug="my-bug", title="New finding")
        with patch.object(_defer_mod, "BACKLOG_DIR", tmp_path / ".backlog"), \
             patch.object(_defer_mod, "ITEMS_DIR", tmp_path / ".backlog" / "items"), \
             patch.object(_defer_mod, "ARCHIVE_DIR", tmp_path / ".backlog" / "archive"):
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                cmd_link_finding(args)

        content = step.read_text()
        assert "Existing finding" in content
        assert "[DEFER] New finding" in content

    def test_nonexistent_step_file(self, tmp_path):
        _bootstrap(tmp_path)
        with pytest.raises(SystemExit):
            args = Namespace(step_file=str(tmp_path / "nope.md"), slug="slug", title="title")
            with patch.object(_defer_mod, "BACKLOG_DIR", tmp_path / ".backlog"), \
                 patch.object(_defer_mod, "ITEMS_DIR", tmp_path / ".backlog" / "items"), \
                 patch.object(_defer_mod, "ARCHIVE_DIR", tmp_path / ".backlog" / "archive"):
                buf = io.StringIO()
                with patch("sys.stdout", buf), patch("sys.stderr", io.StringIO()):
                    cmd_link_finding(args)

    def test_relative_path_from_nested_step(self, tmp_path):
        proto_dir = tmp_path / ".protocols" / "0001" / "02-group"
        proto_dir.mkdir(parents=True)
        step = proto_dir / "01-task.md"
        step.write_text("# Task\n\n## Findings\n\n")
        _create(tmp_path, "Deep item", type_="debt", priority="p2")

        args = Namespace(step_file=str(step), slug="deep-item", title="Deep item")
        with patch.object(_defer_mod, "BACKLOG_DIR", tmp_path / ".backlog"), \
             patch.object(_defer_mod, "ITEMS_DIR", tmp_path / ".backlog" / "items"), \
             patch.object(_defer_mod, "ARCHIVE_DIR", tmp_path / ".backlog" / "archive"):
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                cmd_link_finding(args)
            out = json.loads(buf.getvalue())

        rel = out["relative_path"]
        assert rel.startswith("../../../.backlog/") or rel.startswith("..\\..\\..\\"), \
            f"Expected 3 levels up, got: {rel}"


# --- Helpers (direct unit tests) ---

class TestSlugify:
    def test_basic_title(self):
        assert slugify("Fix login bug") == "fix-login-bug"

    def test_strips_special_chars(self):
        assert slugify("is_admin_user() returns False") == "isadminuser-returns-false"

    def test_collapses_whitespace_and_dashes(self):
        assert slugify("  too   many   spaces  ") == "too-many-spaces"

    def test_truncates_long_titles(self):
        slug = slugify("A" * 100)
        assert len(slug) <= 60

    def test_non_ascii_falls_back_to_hash(self):
        slug = slugify("Тестовая задача")
        assert slug.startswith("item-")

    def test_empty_string_falls_back_to_hash(self):
        slug = slugify("")
        assert slug.startswith("item-")

    def test_em_dash_and_special(self):
        slug = slugify("broken — thing")
        assert slug == "broken-thing"


class TestYamlEscape:
    def test_plain_string_unchanged(self):
        assert yaml_escape("hello world") == "hello world"

    def test_empty_string(self):
        assert yaml_escape("") == '""'

    def test_colon_quoted(self):
        result = yaml_escape("key: value")
        assert result.startswith('"') and result.endswith('"')
        assert "key: value" in result

    def test_double_quotes_escaped(self):
        result = yaml_escape('say "hello"')
        assert result.startswith('"')
        assert '\\"' in result

    def test_newline_escaped(self):
        result = yaml_escape("line1\nline2")
        assert "\\n" in result
        assert result.startswith('"')

    def test_leading_dash_quoted(self):
        result = yaml_escape("- list item")
        assert result.startswith('"')

    def test_round_trip_with_quotes(self):
        import yaml
        original = 'Fix "broken" auth'
        escaped = yaml_escape(original)
        parsed = yaml.safe_load(f"title: {escaped}")
        assert parsed["title"] == original

    def test_round_trip_with_colon(self):
        import yaml
        original = "protocol: step-03: substep"
        escaped = yaml_escape(original)
        parsed = yaml.safe_load(f"origin: {escaped}")
        assert parsed["origin"] == original


# --- Parse Frontmatter ---

class TestParseFrontmatter:
    def test_strips_inline_comments(self, tmp_path):
        _bootstrap(tmp_path)
        item_path = tmp_path / ".backlog" / "items" / "test-comments.md"
        item_path.write_text(
            "---\n"
            "title: Test\n"
            "type: bug  # bug | debt | idea | risk\n"
            "priority: p1  # p0 (critical) | p1 (high)\n"
            "status: open  # open | scheduled | closed\n"
            "area: api\n"
            "effort: s  # xs | s | m | l | xl\n"
            "origin: test\n"
            "created: 2026-01-01\n"
            "---\n"
        )
        out = _list(tmp_path)
        item = next(i for i in out["items"] if i["slug"] == "test-comments")
        assert item["type"] == "bug"
        assert item["priority"] == "p1"
        assert item["status"] == "open"
        assert item["effort"] == "s"


# --- CLI contract smoke tests (subprocess) ---

@pytest.mark.e2e
class TestCLIContract:
    """Verify CLI argument parsing, exit codes, and JSON output format."""

    def test_create_outputs_json(self, tmp_path):
        out = run_defer("create", "--title", "Test", "--type", "bug",
                        "--priority", "p1", cwd=tmp_path)
        assert out["action"] == "create"
        assert out["slug"] == "test"

    def test_list_outputs_json(self, tmp_path):
        run_defer("create", "--title", "A", "--type", "bug", "--priority", "p1", cwd=tmp_path)
        out = run_defer("list", cwd=tmp_path)
        assert out["action"] == "list"
        assert out["count"] == 1

    def test_invalid_type_exits_nonzero(self, tmp_path):
        result = run_defer_raw("create", "--title", "T", "--type", "bad", "--priority", "p1",
                               cwd=tmp_path)
        assert result.returncode != 0
