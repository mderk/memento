#!/usr/bin/env python3
"""Tests for the defer backlog script."""

import json
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

SCRIPT = Path(__file__).resolve().parent.parent / "static" / "skills" / "defer" / "scripts" / "defer.py"


def run(args: list[str], cwd: str) -> dict:
    """Run defer.py with args in given cwd, return parsed JSON."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)] + args,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    output = result.stdout + result.stderr
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        raise RuntimeError(f"Script output not JSON (exit {result.returncode}): {output}")


def run_raw(args: list[str], cwd: str) -> subprocess.CompletedProcess:
    """Run defer.py and return raw result."""
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + args,
        capture_output=True,
        text=True,
        cwd=cwd,
    )


# --- Bootstrap ---

class TestBootstrap:
    def test_creates_scaffolding(self):
        with TemporaryDirectory() as tmp:
            out = run(["bootstrap"], tmp)
            assert out["action"] == "bootstrap"
            assert out["already_existed"] is False
            assert (Path(tmp) / ".backlog" / "README.md").exists()
            assert (Path(tmp) / ".backlog" / "templates" / "item.md").exists()
            assert (Path(tmp) / ".backlog" / "items").is_dir()
            assert (Path(tmp) / ".backlog" / "archive").is_dir()

    def test_idempotent(self):
        with TemporaryDirectory() as tmp:
            run(["bootstrap"], tmp)
            out = run(["bootstrap"], tmp)
            assert out["already_existed"] is True
            assert out["created"] == []


# --- Create ---

class TestCreate:
    def test_basic_create(self):
        with TemporaryDirectory() as tmp:
            out = run([
                "create",
                "--title", "Fix login bug",
                "--type", "bug",
                "--priority", "p1",
                "--origin", "code-review",
            ], tmp)
            assert out["action"] == "create"
            assert out["slug"] == "fix-login-bug"
            assert out["type"] == "bug"
            item = Path(tmp) / out["path"]
            assert item.exists()
            content = item.read_text()
            assert "Fix login bug" in content
            assert "type: bug" in content
            assert "status: open" in content

    def test_auto_bootstrap_then_creates_item(self):
        """BLOCKER regression: create must not exit after bootstrap."""
        with TemporaryDirectory() as tmp:
            out = run([
                "create",
                "--title", "Test item",
                "--type", "idea",
                "--priority", "p3",
            ], tmp)
            assert out["action"] == "create", f"Expected create, got {out.get('action')}"
            assert (Path(tmp) / ".backlog" / "README.md").exists()
            assert (Path(tmp) / out["path"]).exists()
            assert "bootstrapped" in out

    def test_duplicate_slug(self):
        with TemporaryDirectory() as tmp:
            out1 = run(["create", "--title", "Same title", "--type", "debt", "--priority", "p2"], tmp)
            out2 = run(["create", "--title", "Same title", "--type", "risk", "--priority", "p0"], tmp)
            assert out1["slug"] == "same-title"
            assert out2["slug"] == "same-title-2"
            assert (Path(tmp) / out1["path"]).exists()
            assert (Path(tmp) / out2["path"]).exists()

    def test_invalid_type(self):
        with TemporaryDirectory() as tmp:
            result = run_raw(["create", "--title", "X", "--type", "invalid", "--priority", "p0"], tmp)
            assert result.returncode != 0

    def test_description_included(self):
        with TemporaryDirectory() as tmp:
            out = run([
                "create", "--title", "Auth coupling", "--type", "debt",
                "--priority", "p2", "--description", "Direct DB calls in auth module",
            ], tmp)
            content = (Path(tmp) / out["path"]).read_text()
            assert "Direct DB calls in auth module" in content

    def test_slug_special_chars(self):
        with TemporaryDirectory() as tmp:
            out = run([
                "create", "--title", 'Fix bug: UTF-8 (encoding) & "special" chars!',
                "--type", "bug", "--priority", "p1",
            ], tmp)
            assert re.search(r"^[a-z0-9-]+$", out["slug"])

    def test_slug_truncation(self):
        with TemporaryDirectory() as tmp:
            out = run([
                "create", "--title", "a very long title " * 10,
                "--type", "idea", "--priority", "p3",
            ], tmp)
            assert len(out["slug"]) <= 60

    def test_yaml_escaping_quotes_in_title(self):
        """REQUIRED: titles with quotes must produce valid YAML."""
        with TemporaryDirectory() as tmp:
            out = run([
                "create", "--title", 'Fix "broken" auth',
                "--type", "bug", "--priority", "p1",
            ], tmp)
            content = (Path(tmp) / out["path"]).read_text()
            # Must not have unescaped quotes breaking frontmatter
            assert "---" in content
            assert 'Fix \\"broken\\" auth' in content or "Fix" in content

    def test_yaml_escaping_colon_in_origin(self):
        """REQUIRED: origins with colons must produce valid YAML."""
        with TemporaryDirectory() as tmp:
            out = run([
                "create", "--title", "Test", "--type", "debt",
                "--priority", "p2", "--origin", "protocol: step-03: substep",
            ], tmp)
            content = (Path(tmp) / out["path"]).read_text()
            assert "protocol" in content
            # Should be quoted in frontmatter
            assert '"' in content.split("origin:")[1].split("\n")[0]

    def test_yaml_escaping_newline_in_title(self):
        """REQUIRED: newlines in title must be escaped, not break frontmatter."""
        with TemporaryDirectory() as tmp:
            out = run([
                "create", "--title", "Line one\nLine two", "--type", "bug", "--priority", "p1",
            ], tmp)
            content = (Path(tmp) / out["path"]).read_text()
            # Frontmatter must have exactly two --- delimiters
            parts = content.split("---")
            assert len(parts) >= 3, f"Frontmatter broken by newline: {content[:200]}"
            # Newline must be escaped as \n inside quotes
            title_line = [l for l in parts[1].splitlines() if l.strip().startswith("title:")][0]
            assert "\\n" in title_line

    def test_non_ascii_title_gets_hash_slug(self):
        """SUGGESTION: non-ASCII titles should not all become 'untitled'."""
        with TemporaryDirectory() as tmp:
            out1 = run(["create", "--title", "Рефакторинг модуля", "--type", "debt", "--priority", "p2"], tmp)
            out2 = run(["create", "--title", "Другая задача", "--type", "idea", "--priority", "p3"], tmp)
            assert out1["slug"] != out2["slug"], "Different titles must produce different slugs"
            assert out1["slug"].startswith("item-")
            assert (Path(tmp) / out1["path"]).exists()


# --- Close ---

class TestClose:
    def test_close_moves_to_archive(self):
        with TemporaryDirectory() as tmp:
            out = run(["create", "--title", "To close", "--type", "bug", "--priority", "p1"], tmp)
            slug = out["slug"]
            close_out = run(["close", slug], tmp)
            assert close_out["action"] == "close"
            assert not (Path(tmp) / ".backlog" / "items" / f"{slug}.md").exists()
            archived = Path(tmp) / ".backlog" / "archive" / f"{slug}.md"
            assert archived.exists()
            assert "status: closed" in archived.read_text()

    def test_close_nonexistent(self):
        with TemporaryDirectory() as tmp:
            run(["bootstrap"], tmp)
            result = run_raw(["close", "nonexistent"], tmp)
            assert result.returncode != 0


# --- List ---

class TestList:
    def test_list_all(self):
        with TemporaryDirectory() as tmp:
            run(["create", "--title", "A", "--type", "bug", "--priority", "p0"], tmp)
            run(["create", "--title", "B", "--type", "idea", "--priority", "p3"], tmp)
            out = run(["list"], tmp)
            assert out["count"] == 2

    def test_list_with_status_filter(self):
        with TemporaryDirectory() as tmp:
            run(["create", "--title", "A", "--type", "bug", "--priority", "p0"], tmp)
            run(["create", "--title", "B", "--type", "idea", "--priority", "p3"], tmp)
            run(["close", "a"], tmp)
            out = run(["list", "--status", "open"], tmp)
            assert out["count"] == 1

    def test_list_empty(self):
        with TemporaryDirectory() as tmp:
            run(["bootstrap"], tmp)
            out = run(["list"], tmp)
            assert out["count"] == 0
            assert out["items"] == []

    def test_list_no_backlog_dir(self):
        """SUGGESTION: list should not crash when .backlog/ doesn't exist."""
        with TemporaryDirectory() as tmp:
            out = run(["list"], tmp)
            assert out["count"] == 0


# --- Link Finding ---

class TestLinkFinding:
    def test_inserts_into_existing_findings(self):
        with TemporaryDirectory() as tmp:
            step = Path(tmp) / "step-03.md"
            step.write_text("# Step 03\n\nWork.\n\n## Findings\n\n-   [GOTCHA] Something\n")
            run(["create", "--title", "Cache bug", "--type", "bug", "--priority", "p1"], tmp)
            out = run(["link-finding", str(step), "cache-bug", "Cache bug"], tmp)
            content = step.read_text()
            assert "[DEFER] Cache bug" in content
            assert "[GOTCHA] Something" in content

    def test_creates_findings_section(self):
        with TemporaryDirectory() as tmp:
            step = Path(tmp) / "step-01.md"
            step.write_text("# Step 01\n\nJust work, no findings yet.\n")
            run(["link-finding", str(step), "my-item", "My item"], tmp)
            content = step.read_text()
            assert "## Findings" in content
            assert "[DEFER] My item" in content

    def test_produces_valid_markdown_link(self):
        """REQUIRED: link must be a valid markdown link, not bare brackets."""
        with TemporaryDirectory() as tmp:
            step = Path(tmp) / "step.md"
            step.write_text("# Step\n\n## Findings\n\n")
            run(["create", "--title", "Test", "--type", "bug", "--priority", "p1"], tmp)
            run(["link-finding", str(step), "test", "Test"], tmp)
            content = step.read_text()
            # Must contain [text](path) format
            assert re.search(r"\[.*\]\(.*\.backlog/items/test\.md\)", content), \
                f"Expected valid markdown link in: {content}"

    def test_relative_path_from_nested_step(self):
        """REQUIRED: path must be relative from step file to .backlog/."""
        with TemporaryDirectory() as tmp:
            proto_dir = Path(tmp) / ".protocols" / "0001" / "02-group"
            proto_dir.mkdir(parents=True)
            step = proto_dir / "01-task.md"
            step.write_text("# Task\n\n## Findings\n\n")
            run(["create", "--title", "Deep item", "--type", "debt", "--priority", "p2"], tmp)
            out = run(["link-finding", str(step), "deep-item", "Deep item"], tmp)
            rel = out["relative_path"]
            # From .protocols/0001/02-group/ to .backlog/items/ needs ../../../
            assert rel.startswith("../../../.backlog/") or rel.startswith("..\\..\\..\\"), \
                f"Expected 3 levels up, got: {rel}"

    def test_nonexistent_step_file(self):
        with TemporaryDirectory() as tmp:
            result = run_raw(["link-finding", "/no/such/file.md", "slug", "title"], tmp)
            assert result.returncode != 0


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
