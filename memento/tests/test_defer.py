"""Tests for defer.py backlog management script."""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "static"
    / "skills"
    / "defer"
    / "scripts"
    / "defer.py"
)


def run_defer(*args: str, cwd: Path) -> dict:
    """Run defer.py as subprocess, return parsed JSON output."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=cwd,
    )
    if result.returncode != 0:
        # Error JSON goes to stderr
        try:
            return {**json.loads(result.stderr), "_rc": result.returncode}
        except json.JSONDecodeError:
            raise AssertionError(
                f"defer.py failed (rc={result.returncode}):\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )
    return json.loads(result.stdout)


def run_defer_raw(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    """Run defer.py, return raw CompletedProcess."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=cwd,
    )


# --- Bootstrap ---

class TestBootstrap:
    def test_creates_scaffolding(self, tmp_path):
        out = run_defer("bootstrap", cwd=tmp_path)
        assert out["action"] == "bootstrap"
        assert out["already_existed"] is False
        assert (tmp_path / ".backlog" / "items").is_dir()
        assert (tmp_path / ".backlog" / "archive").is_dir()
        assert (tmp_path / ".backlog" / "templates" / "item.md").exists()
        assert (tmp_path / ".backlog" / "README.md").exists()

    def test_idempotent(self, tmp_path):
        run_defer("bootstrap", cwd=tmp_path)
        out = run_defer("bootstrap", cwd=tmp_path)
        assert out["already_existed"] is True
        assert out["created"] == []


# --- Create ---

class TestCreate:
    def test_basic_create(self, tmp_path):
        out = run_defer(
            "create", "--title", "Fix login bug",
            "--type", "bug", "--priority", "p1",
            cwd=tmp_path,
        )
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
        out = run_defer(
            "create", "--title", "Add caching",
            "--type", "debt", "--priority", "p2",
            "--area", "api", "--effort", "m",
            cwd=tmp_path,
        )
        assert out["area"] == "api"
        assert out["effort"] == "m"

        content = (tmp_path / ".backlog" / "items" / "add-caching.md").read_text()
        assert "area: api" in content
        assert "effort: m" in content

    def test_create_with_description(self, tmp_path):
        out = run_defer(
            "create", "--title", "Add rate limiting",
            "--type", "idea", "--priority", "p3",
            "--description", "Need rate limiting on public endpoints",
            cwd=tmp_path,
        )
        content = (tmp_path / ".backlog" / "items" / f"{out['slug']}.md").read_text()
        assert "Need rate limiting on public endpoints" in content

    def test_create_with_origin(self, tmp_path):
        out = run_defer(
            "create", "--title", "SQL injection risk",
            "--type", "risk", "--priority", "p0",
            "--origin", ".protocols/0005/03-api.md",
            cwd=tmp_path,
        )
        assert out["origin"] == ".protocols/0005/03-api.md"
        content = (tmp_path / ".backlog" / "items" / f"{out['slug']}.md").read_text()
        assert ".protocols/0005/03-api.md" in content

    def test_invalid_type(self, tmp_path):
        result = run_defer_raw(
            "create", "--title", "Test",
            "--type", "invalid", "--priority", "p1",
            cwd=tmp_path,
        )
        assert result.returncode != 0
        assert "invalid choice" in result.stderr

    def test_invalid_effort(self, tmp_path):
        out = run_defer(
            "create", "--title", "Test",
            "--type", "bug", "--priority", "p1",
            "--effort", "xxl",
            cwd=tmp_path,
        )
        assert out["_rc"] != 0
        assert "error" in out

    def test_duplicate_slug_gets_suffix(self, tmp_path):
        run_defer("create", "--title", "Fix bug", "--type", "bug", "--priority", "p1", cwd=tmp_path)
        out = run_defer("create", "--title", "Fix bug", "--type", "debt", "--priority", "p2", cwd=tmp_path)
        assert out["slug"] == "fix-bug-2"
        assert (tmp_path / ".backlog" / "items" / "fix-bug.md").exists()
        assert (tmp_path / ".backlog" / "items" / "fix-bug-2.md").exists()

    def test_special_chars_in_title(self, tmp_path):
        out = run_defer(
            "create", "--title", "is_admin_user() returns False — broken",
            "--type", "bug", "--priority", "p1",
            cwd=tmp_path,
        )
        assert out["slug"]  # non-empty
        assert (tmp_path / ".backlog" / "items" / f"{out['slug']}.md").exists()

    def test_non_ascii_title(self, tmp_path):
        out = run_defer(
            "create", "--title", "Тестовая задача",
            "--type", "idea", "--priority", "p3",
            cwd=tmp_path,
        )
        # Non-ASCII falls back to hash-based slug
        assert out["slug"].startswith("item-")
        assert (tmp_path / ".backlog" / "items" / f"{out['slug']}.md").exists()

    def test_bootstraps_automatically(self, tmp_path):
        """Create should bootstrap .backlog/ if it doesn't exist."""
        assert not (tmp_path / ".backlog").exists()
        out = run_defer("create", "--title", "Test", "--type", "bug", "--priority", "p1", cwd=tmp_path)
        assert (tmp_path / ".backlog" / "items").is_dir()
        assert "bootstrapped" in out

    def test_yaml_escaping_quotes_in_title(self, tmp_path):
        """Titles with quotes must produce valid YAML."""
        out = run_defer(
            "create", "--title", 'Fix "broken" auth',
            "--type", "bug", "--priority", "p1",
            cwd=tmp_path,
        )
        content = (tmp_path / ".backlog" / "items" / f"{out['slug']}.md").read_text()
        assert "---" in content
        assert "Fix" in content

    def test_yaml_escaping_colon_in_origin(self, tmp_path):
        """Origins with colons must produce valid YAML."""
        out = run_defer(
            "create", "--title", "Test", "--type", "debt",
            "--priority", "p2", "--origin", "protocol: step-03: substep",
            cwd=tmp_path,
        )
        content = (tmp_path / ".backlog" / "items" / f"{out['slug']}.md").read_text()
        assert "protocol" in content
        assert '"' in content.split("origin:")[1].split("\n")[0]

    def test_yaml_escaping_newline_in_title(self, tmp_path):
        """Newlines in title must be escaped, not break frontmatter."""
        out = run_defer(
            "create", "--title", "Line one\nLine two",
            "--type", "bug", "--priority", "p1",
            cwd=tmp_path,
        )
        content = (tmp_path / ".backlog" / "items" / f"{out['slug']}.md").read_text()
        parts = content.split("---")
        assert len(parts) >= 3, f"Frontmatter broken by newline: {content[:200]}"
        title_line = [l for l in parts[1].splitlines() if l.strip().startswith("title:")][0]
        assert "\\n" in title_line


# --- Close ---

class TestClose:
    def test_close_moves_to_archive(self, tmp_path):
        run_defer("create", "--title", "Old bug", "--type", "bug", "--priority", "p2", cwd=tmp_path)
        out = run_defer("close", "old-bug", cwd=tmp_path)
        assert out["action"] == "close"
        assert not (tmp_path / ".backlog" / "items" / "old-bug.md").exists()
        archived = tmp_path / ".backlog" / "archive" / "old-bug.md"
        assert archived.exists()
        assert "status: closed" in archived.read_text()

    def test_close_nonexistent(self, tmp_path):
        run_defer("bootstrap", cwd=tmp_path)
        out = run_defer("close", "nonexistent", cwd=tmp_path)
        assert out["_rc"] != 0
        assert "error" in out


# --- List ---

class TestList:
    def _seed(self, tmp_path):
        """Create a few items for listing tests."""
        run_defer("create", "--title", "Bug A", "--type", "bug", "--priority", "p1",
                  "--area", "api", cwd=tmp_path)
        run_defer("create", "--title", "Debt B", "--type", "debt", "--priority", "p2",
                  "--area", "api", "--effort", "s", cwd=tmp_path)
        run_defer("create", "--title", "Idea C", "--type", "idea", "--priority", "p3",
                  "--area", "ui", cwd=tmp_path)

    def test_list_all(self, tmp_path):
        self._seed(tmp_path)
        out = run_defer("list", cwd=tmp_path)
        assert out["count"] == 3

    def test_list_empty(self, tmp_path):
        run_defer("bootstrap", cwd=tmp_path)
        out = run_defer("list", cwd=tmp_path)
        assert out["count"] == 0
        assert out["items"] == []

    def test_list_no_backlog_dir(self, tmp_path):
        """list should not crash when .backlog/ doesn't exist."""
        out = run_defer("list", cwd=tmp_path)
        assert out["count"] == 0

    def test_filter_by_type(self, tmp_path):
        self._seed(tmp_path)
        out = run_defer("list", "--type", "bug", cwd=tmp_path)
        assert out["count"] == 1
        assert out["items"][0]["title"] == "Bug A"

    def test_filter_by_area(self, tmp_path):
        self._seed(tmp_path)
        out = run_defer("list", "--area", "api", cwd=tmp_path)
        assert out["count"] == 2

    def test_filter_by_priority(self, tmp_path):
        self._seed(tmp_path)
        out = run_defer("list", "--priority", "p3", cwd=tmp_path)
        assert out["count"] == 1
        assert out["items"][0]["title"] == "Idea C"

    def test_filter_by_effort(self, tmp_path):
        self._seed(tmp_path)
        out = run_defer("list", "--effort", "s", cwd=tmp_path)
        assert out["count"] == 1
        assert out["items"][0]["title"] == "Debt B"

    def test_filter_by_status(self, tmp_path):
        self._seed(tmp_path)
        run_defer("close", "bug-a", cwd=tmp_path)
        out = run_defer("list", "--status", "open", cwd=tmp_path)
        assert out["count"] == 2

    def test_combined_filters(self, tmp_path):
        self._seed(tmp_path)
        out = run_defer("list", "--type", "debt", "--area", "api", cwd=tmp_path)
        assert out["count"] == 1
        assert out["items"][0]["title"] == "Debt B"

    def test_no_match(self, tmp_path):
        self._seed(tmp_path)
        out = run_defer("list", "--area", "nonexistent", cwd=tmp_path)
        assert out["count"] == 0

    def test_list_includes_area_and_effort(self, tmp_path):
        self._seed(tmp_path)
        out = run_defer("list", cwd=tmp_path)
        item_b = next(i for i in out["items"] if i["title"] == "Debt B")
        assert item_b["area"] == "api"
        assert item_b["effort"] == "s"


# --- View ---

class TestView:
    def _seed(self, tmp_path):
        """Create items for view tests."""
        run_defer("create", "--title", "Critical bug", "--type", "bug", "--priority", "p1",
                  "--area", "api", "--effort", "s", cwd=tmp_path)
        run_defer("create", "--title", "Low debt", "--type", "debt", "--priority", "p3",
                  "--area", "api", cwd=tmp_path)
        run_defer("create", "--title", "UI idea", "--type", "idea", "--priority", "p2",
                  "--area", "ui", cwd=tmp_path)

    def test_view_to_file(self, tmp_path):
        self._seed(tmp_path)
        out_path = str(tmp_path / ".backlog" / "views" / "by-priority.md")
        out = run_defer("view", "--group-by", "priority", "-o", out_path, cwd=tmp_path)
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
        result = run_defer_raw("view", "--group-by", "type", cwd=tmp_path)
        assert result.returncode == 0
        assert "## bug" in result.stdout
        assert "## debt" in result.stdout
        assert "## idea" in result.stdout

    def test_view_group_by_area(self, tmp_path):
        self._seed(tmp_path)
        out_path = str(tmp_path / ".backlog" / "views" / "by-area.md")
        out = run_defer("view", "--group-by", "area", "-o", out_path, cwd=tmp_path)
        assert out["groups"] == 2  # api, ui
        content = Path(out_path).read_text()
        assert "## api (2)" in content
        assert "## ui (1)" in content

    def test_view_with_filter(self, tmp_path):
        self._seed(tmp_path)
        out_path = str(tmp_path / ".backlog" / "views" / "filtered.md")
        out = run_defer("view", "--group-by", "type", "--area", "api", "-o", out_path, cwd=tmp_path)
        assert out["items"] == 2
        content = Path(out_path).read_text()
        assert "(area=api)" in content
        assert "UI idea" not in content

    def test_view_excludes_group_by_column(self, tmp_path):
        self._seed(tmp_path)
        result = run_defer_raw("view", "--group-by", "priority", cwd=tmp_path)
        # "Priority" should not appear as a table column when grouping by priority
        lines = result.stdout.splitlines()
        header_lines = [l for l in lines if l.startswith("| # |")]
        for h in header_lines:
            assert "Priority" not in h

    def test_view_priority_order(self, tmp_path):
        """p1 section should appear before p3."""
        self._seed(tmp_path)
        result = run_defer_raw("view", "--group-by", "priority", cwd=tmp_path)
        p1_pos = result.stdout.index("## p1")
        p2_pos = result.stdout.index("## p2")
        p3_pos = result.stdout.index("## p3")
        assert p1_pos < p2_pos < p3_pos

    def test_view_contains_regen_command(self, tmp_path):
        self._seed(tmp_path)
        out_path = str(tmp_path / ".backlog" / "views" / "test.md")
        run_defer("view", "--group-by", "area", "--type", "bug", "-o", out_path, cwd=tmp_path)
        content = Path(out_path).read_text()
        assert "Regenerate:" in content
        assert "--group-by area" in content
        assert "--type bug" in content

    def test_view_links_to_items(self, tmp_path):
        self._seed(tmp_path)
        result = run_defer_raw("view", "--group-by", "type", cwd=tmp_path)
        assert "../items/critical-bug.md" in result.stdout

    def test_view_empty_field_shows_none(self, tmp_path):
        run_defer("create", "--title", "No area", "--type", "bug", "--priority", "p1", cwd=tmp_path)
        result = run_defer_raw("view", "--group-by", "area", cwd=tmp_path)
        assert "## (none)" in result.stdout


# --- Link Finding ---

class TestLinkFinding:
    def test_appends_findings_section(self, tmp_path):
        (tmp_path / ".backlog" / "items").mkdir(parents=True)
        (tmp_path / ".backlog" / "items" / "my-bug.md").write_text("---\ntitle: My Bug\n---\n")
        step = tmp_path / "step-03.md"
        step.write_text("# Step 3\n\nSome content\n")

        out = run_defer("link-finding", str(step), "my-bug", "My Bug Title", cwd=tmp_path)
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

        run_defer("link-finding", str(step), "my-bug", "New finding", cwd=tmp_path)
        content = step.read_text()
        assert "Existing finding" in content
        assert "[DEFER] New finding" in content

    def test_nonexistent_step_file(self, tmp_path):
        run_defer("bootstrap", cwd=tmp_path)
        out = run_defer("link-finding", str(tmp_path / "nope.md"), "slug", "title", cwd=tmp_path)
        assert out["_rc"] != 0

    def test_relative_path_from_nested_step(self, tmp_path):
        """Path must be relative from step file to .backlog/."""
        proto_dir = tmp_path / ".protocols" / "0001" / "02-group"
        proto_dir.mkdir(parents=True)
        step = proto_dir / "01-task.md"
        step.write_text("# Task\n\n## Findings\n\n")
        run_defer("create", "--title", "Deep item", "--type", "debt", "--priority", "p2", cwd=tmp_path)
        out = run_defer("link-finding", str(step), "deep-item", "Deep item", cwd=tmp_path)
        rel = out["relative_path"]
        assert rel.startswith("../../../.backlog/") or rel.startswith("..\\..\\..\\"), \
            f"Expected 3 levels up, got: {rel}"


# --- Helpers ---

class TestSlugify:
    """Test slug generation via create command (integration)."""

    def test_long_title_truncated(self, tmp_path):
        long_title = "A" * 100
        out = run_defer("create", "--title", long_title, "--type", "bug", "--priority", "p1", cwd=tmp_path)
        assert len(out["slug"]) <= 60

    def test_yaml_special_chars_escaped(self, tmp_path):
        out = run_defer(
            "create", "--title", 'Title with "quotes" and: colons',
            "--type", "bug", "--priority", "p1",
            cwd=tmp_path,
        )
        item = tmp_path / ".backlog" / "items" / f"{out['slug']}.md"
        content = item.read_text()
        assert "quotes" in content
        assert "colons" in content


# --- Parse Frontmatter ---

class TestParseFrontmatter:
    def test_strips_inline_comments(self, tmp_path):
        """Inline comments in frontmatter (e.g. from template) should be stripped."""
        run_defer("bootstrap", cwd=tmp_path)
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
        out = run_defer("list", cwd=tmp_path)
        item = next(i for i in out["items"] if i["slug"] == "test-comments")
        assert item["type"] == "bug"
        assert item["priority"] == "p1"
        assert item["status"] == "open"
        assert item["effort"] == "s"
