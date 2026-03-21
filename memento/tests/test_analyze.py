#!/usr/bin/env python3
"""Tests for the analyze-local-changes skill script."""

import json
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "analyze-local-changes"
    / "scripts"
    / "analyze.py"
)

# Load functions directly for unit tests
_code = SCRIPT.read_text()
_ns: dict = {}
exec(compile(_code, str(SCRIPT), "exec"), _ns)

parse_sections_for_merge = _ns["parse_sections_for_merge"]
sections_content_equal = _ns["sections_content_equal"]
render_sections = _ns["render_sections"]
merge_markdown_3way = _ns["merge_markdown_3way"]
parse_plan_metadata_fn = _ns["parse_plan_metadata"]
update_plan_metadata_fn = _ns["update_plan_metadata"]
compute_hash = _ns["compute_hash"]
parse_generation_plan = _ns["parse_generation_plan"]
evaluate_conditional = _ns["evaluate_conditional"]
parse_prompt_frontmatter = _ns["parse_prompt_frontmatter"]
parse_manifest = _ns["parse_manifest"]
classify_static_files = _ns["classify_static_files"]
compare_tech_stacks = _ns["compare_tech_stacks"]
detect_obsolete_files = _ns["detect_obsolete_files"]
load_project_analysis = _ns["load_project_analysis"]
cmd_merge = _ns["cmd_merge"]
cmd_pre_update = _ns["cmd_pre_update"]
cmd_copy_static = _ns["cmd_copy_static"]
cmd_check_existing = _ns["cmd_check_existing"]
cmd_plan_generation = _ns["cmd_plan_generation"]
git_show = _ns["git_show"]

# Patch GENERATION_PLAN for metadata tests
GENERATION_PLAN_REF = _ns


def run(args: list[str], cwd: str) -> dict:
    """Run analyze.py with args in given cwd, return parsed JSON."""
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
        raise RuntimeError(
            f"Script output not JSON (exit {result.returncode}): {output}"
        )


def run_raw(args: list[str], cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + args,
        capture_output=True,
        text=True,
        cwd=cwd,
    )


# ============ parse_sections_for_merge ============


class TestParseSections:
    def test_basic_sections(self):
        md = "# Title\n\nIntro.\n\n## A\n\nContent A.\n\n## B\n\nContent B."
        secs = parse_sections_for_merge(md)
        assert len(secs) == 3
        assert secs[0]["header"] == "# Title"
        assert secs[1]["header"] == "## A"
        assert secs[2]["header"] == "## B"

    def test_preamble_preserved(self):
        md = "Some preamble text.\n\n# Title\n\nContent."
        secs = parse_sections_for_merge(md)
        assert len(secs) == 2
        assert secs[0]["header"] == ""
        assert "preamble" in secs[0]["content"]
        assert secs[1]["header"] == "# Title"

    def test_empty_content(self):
        secs = parse_sections_for_merge("")
        assert secs == []

    def test_no_headers(self):
        md = "Just plain text.\nAnother line."
        secs = parse_sections_for_merge(md)
        assert len(secs) == 1
        assert secs[0]["header"] == ""
        assert "plain text" in secs[0]["content"]

    def test_nested_headers(self):
        md = "# H1\n\n## H2\n\nContent.\n\n### H3\n\nDeep."
        secs = parse_sections_for_merge(md)
        assert len(secs) == 3
        assert secs[0]["header"] == "# H1"
        assert secs[1]["header"] == "## H2"
        assert secs[2]["header"] == "### H3"

    def test_header_not_in_code_block(self):
        """Lines starting with # inside normal text are still treated as headers.
        This is a known limitation — we do section-level merge, not full markdown parse."""
        md = "# Title\n\nSome text.\n\n## Real Section\n\nContent."
        secs = parse_sections_for_merge(md)
        assert any(s["header"] == "## Real Section" for s in secs)


# ============ render_sections ============


class TestRenderSections:
    def test_roundtrip(self):
        md = "# Title\n\nIntro.\n\n## A\n\nContent A.\n\n## B\n\nContent B."
        secs = parse_sections_for_merge(md)
        rendered = render_sections(secs)
        assert rendered == md

    def test_roundtrip_with_preamble(self):
        md = "Preamble.\n\n# Title\n\nContent."
        secs = parse_sections_for_merge(md)
        rendered = render_sections(secs)
        assert rendered == md

    def test_empty(self):
        assert render_sections([]) == ""


# ============ merge_markdown_3way ============


class TestMerge3Way:
    """Core 3-way merge logic tests."""

    def test_no_changes(self):
        """All three identical → unchanged."""
        md = "# Doc\n\n## A\n\nContent."
        result = merge_markdown_3way(md, md, md)
        assert result["status"] == "merged"
        assert result["stats"]["unchanged"] == 2
        assert result["stats"]["conflicts"] == 0

    def test_only_plugin_changed(self):
        """User didn't touch, plugin updated → take new."""
        base = "# Doc\n\n## A\n\nOld content."
        local = base
        new = "# Doc\n\n## A\n\nNew content."
        result = merge_markdown_3way(base, local, new)
        assert result["status"] == "merged"
        assert "New content" in result["merged_content"]
        assert result["stats"]["from_new"] == 1

    def test_only_user_changed(self):
        """Plugin didn't change, user modified → keep local."""
        base = "# Doc\n\n## A\n\nOriginal."
        local = "# Doc\n\n## A\n\nUser modified."
        new = base
        result = merge_markdown_3way(base, local, new)
        assert result["status"] == "merged"
        assert "User modified" in result["merged_content"]
        assert result["stats"]["from_local"] == 1

    def test_both_changed_conflict(self):
        """Both modified same section → conflict."""
        base = "# Doc\n\n## A\n\nOriginal."
        local = "# Doc\n\n## A\n\nUser version."
        new = "# Doc\n\n## A\n\nPlugin version."
        result = merge_markdown_3way(base, local, new)
        assert result["status"] == "conflicts"
        assert len(result["conflicts"]) == 1
        assert result["conflicts"][0]["type"] == "both_modified"
        # Default: keep local for conflicts
        assert "User version" in result["merged_content"]

    def test_user_added_section_preserved(self):
        """User added new section → preserved in merge."""
        base = "# Doc\n\n## A\n\nContent A."
        local = "# Doc\n\n## A\n\nContent A.\n\n## My Custom\n\nUser content."
        new = "# Doc\n\n## A\n\nContent A.\n\n## B\n\nPlugin added B."
        result = merge_markdown_3way(base, local, new)
        assert result["status"] == "merged"
        assert "My Custom" in result["merged_content"]
        assert "Plugin added B" in result["merged_content"]
        assert result["stats"]["user_added"] == 1
        assert result["stats"]["from_new"] == 1

    def test_plugin_added_section(self):
        """Plugin added new section → included."""
        base = "# Doc\n\n## A\n\nContent."
        local = base
        new = "# Doc\n\n## A\n\nContent.\n\n## New Section\n\nFrom plugin."
        result = merge_markdown_3way(base, local, new)
        assert "New Section" in result["merged_content"]
        assert result["stats"]["from_new"] >= 1

    def test_user_deleted_section_conflict(self):
        """User deleted section that plugin still has → conflict."""
        base = "# Doc\n\n## A\n\nKeep.\n\n## B\n\nRemove me."
        local = "# Doc\n\n## A\n\nKeep."
        new = "# Doc\n\n## A\n\nKeep.\n\n## B\n\nUpdated B."
        result = merge_markdown_3way(base, local, new)
        assert result["status"] == "conflicts"
        assert any(c["type"] == "user_deleted" for c in result["conflicts"])

    def test_user_section_anchored_correctly(self):
        """User section inserted after correct anchor."""
        base = "## A\n\nA content.\n\n## C\n\nC content."
        local = "## A\n\nA content.\n\n## User Section\n\nCustom.\n\n## C\n\nC content."
        new = "## A\n\nA content.\n\n## C\n\nC content.\n\n## D\n\nNew D."
        result = merge_markdown_3way(base, local, new)
        merged = result["merged_content"]
        # User section should appear after A, before C
        pos_a = merged.index("## A")
        pos_user = merged.index("## User Section")
        pos_c = merged.index("## C")
        assert pos_a < pos_user < pos_c

    def test_repeated_update_preserves_user_additions(self):
        """CRITICAL: User additions from previous merge must survive next update.

        This is the core bug that the two-commit system (Generation Base) solves.
        Base must be the CLEAN plugin output, not the merged result.
        """
        # v1 → v2 update: user added "Our Rules"
        base_v1 = "# Bug Fixing\n\n## Phase 1\n\nReproduce.\n\n## Phase 2\n\nFix."
        local_v1 = (
            "# Bug Fixing\n\n## Phase 1\n\nReproduce.\n\n## Phase 2\n\nFix."
            "\n\n## Our Rules\n\nAlways pair program."
        )
        new_v2 = (
            "# Bug Fixing\n\n## Phase 1\n\nReproduce.\n\n## Phase 2\n\nFix."
            "\n\n## Phase 3\n\nReview."
        )

        merge_v2 = merge_markdown_3way(base_v1, local_v1, new_v2)
        assert "Our Rules" in merge_v2["merged_content"]
        assert "Phase 3" in merge_v2["merged_content"]

        # v2 → v3 update: use CLEAN v2 as base (not merged result!)
        base_clean_v2 = new_v2  # This is what Generation Base stores
        local_after_v2 = merge_v2["merged_content"]  # Merged v2 + user additions
        new_v3 = (
            "# Bug Fixing\n\n## Phase 1\n\nReproduce.\n\n## Phase 2\n\nFix."
            "\n\n## Phase 3\n\nReview.\n\n## Phase 4\n\nDeploy."
        )

        merge_v3 = merge_markdown_3way(base_clean_v2, local_after_v2, new_v3)
        assert merge_v3["status"] == "merged"
        assert "Our Rules" in merge_v3["merged_content"], "User addition was silently dropped!"
        assert "Phase 4" in merge_v3["merged_content"]
        assert merge_v3["stats"]["user_added"] == 1

    def test_bug_with_merged_base_drops_user_additions(self):
        """Demonstrates the bug when using merged result as base."""
        base_v2_merged = (
            "# Bug Fixing\n\n## Phase 1\n\nReproduce.\n\n## Phase 2\n\nFix."
            "\n\n## Our Rules\n\nAlways pair program."
            "\n\n## Phase 3\n\nReview."
        )
        local_unchanged = base_v2_merged  # User didn't change after merge
        new_v3 = (
            "# Bug Fixing\n\n## Phase 1\n\nReproduce.\n\n## Phase 2\n\nFix."
            "\n\n## Phase 3\n\nReview.\n\n## Phase 4\n\nDeploy."
        )

        result = merge_markdown_3way(base_v2_merged, local_unchanged, new_v3)
        # With merged base, "Our Rules" is in base but not in new → treated as "plugin removed"
        # Since base==local for that section, the merge silently drops it
        assert "Our Rules" not in result["merged_content"], (
            "Expected bug: merged base should cause silent drop"
        )

    def test_non_overlapping_changes(self):
        """User changed section A, plugin changed section B → both apply."""
        base = "## A\n\nOriginal A.\n\n## B\n\nOriginal B."
        local = "## A\n\nUser modified A.\n\n## B\n\nOriginal B."
        new = "## A\n\nOriginal A.\n\n## B\n\nPlugin modified B."
        result = merge_markdown_3way(base, local, new)
        assert result["status"] == "merged"
        assert "User modified A" in result["merged_content"]
        assert "Plugin modified B" in result["merged_content"]

    def test_both_added_same_header_conflict(self):
        """Both user and plugin added section with same header → conflict."""
        base = "## A\n\nContent."
        local = "## A\n\nContent.\n\n## New\n\nUser version."
        new = "## A\n\nContent.\n\n## New\n\nPlugin version."
        result = merge_markdown_3way(base, local, new)
        assert result["status"] == "conflicts"
        assert any(c["type"] == "both_added" for c in result["conflicts"])

    def test_multiple_user_sections(self):
        """Multiple user-added sections all preserved."""
        base = "## A\n\nA.\n\n## B\n\nB."
        local = "## A\n\nA.\n\n## User1\n\nU1.\n\n## B\n\nB.\n\n## User2\n\nU2."
        new = "## A\n\nA.\n\n## B\n\nB.\n\n## C\n\nC."
        result = merge_markdown_3way(base, local, new)
        assert "User1" in result["merged_content"]
        assert "User2" in result["merged_content"]
        assert result["stats"]["user_added"] == 2

    def test_plugin_removed_section_user_modified_conflict(self):
        """Plugin removes section that user modified → conflict, keeps local."""
        base = "## A\n\nKeep.\n\n## B\n\nOriginal B.\n\n## C\n\nKeep C."
        local = "## A\n\nKeep.\n\n## B\n\nUser modified B.\n\n## C\n\nKeep C."
        new = "## A\n\nKeep.\n\n## C\n\nKeep C."  # Plugin removed ## B
        result = merge_markdown_3way(base, local, new)
        assert result["status"] == "conflicts"
        assert any(c["type"] == "plugin_removed_user_modified" for c in result["conflicts"])
        # Default: keep local version for conflicts
        assert "User modified B" in result["merged_content"]

    def test_plugin_removed_section_user_unchanged_drops(self):
        """Plugin removes section user didn't touch → silently dropped."""
        base = "## A\n\nKeep.\n\n## B\n\nOriginal B.\n\n## C\n\nKeep C."
        local = "## A\n\nKeep.\n\n## B\n\nOriginal B.\n\n## C\n\nKeep C."
        new = "## A\n\nKeep.\n\n## C\n\nKeep C."  # Plugin removed ## B
        result = merge_markdown_3way(base, local, new)
        assert result["status"] == "merged"
        assert "Original B" not in result["merged_content"]
        assert result["stats"]["conflicts"] == 0

    def test_whitespace_only_difference_not_conflict(self):
        """Trailing whitespace difference should not cause conflict."""
        base = "## A\n\nContent.  "
        local = "## A\n\nContent."
        new = "## A\n\nContent.  "
        result = merge_markdown_3way(base, local, new)
        assert result["stats"]["conflicts"] == 0


# ============ CLI: compute ============


@pytest.mark.e2e
class TestComputeCLI:
    def test_compute_single_file(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("Hello world\n")
        out = run(["compute", str(f)], str(tmp_path))
        assert out["status"] == "success"
        assert len(out["files"]) == 1
        assert out["files"][0]["hash"]
        assert out["files"][0]["lines"] == 1

    def test_compute_missing_file(self, tmp_path):
        out = run(["compute", "/nonexistent/file.md"], str(tmp_path))
        assert out["files"][0]["error"] == "File not found"

    def test_compute_deterministic(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("Same content\n")
        out1 = run(["compute", str(f)], str(tmp_path))
        out2 = run(["compute", str(f)], str(tmp_path))
        assert out1["files"][0]["hash"] == out2["files"][0]["hash"]

    def test_compute_different_content(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("Version 1\n")
        h1 = run(["compute", str(f)], str(tmp_path))["files"][0]["hash"]
        f.write_text("Version 2\n")
        h2 = run(["compute", str(f)], str(tmp_path))["files"][0]["hash"]
        assert h1 != h2


# ============ CLI: detect ============


@pytest.mark.e2e
class TestDetectCLI:
    def _setup_project(self, tmp_path):
        """Create a minimal project with generation-plan.md."""
        mb = tmp_path / ".memory_bank"
        mb.mkdir()
        guides = mb / "guides"
        guides.mkdir()

        f1 = guides / "testing.md"
        f1.write_text("# Testing Guide\n\nContent.\n")

        f2 = guides / "backend.md"
        f2.write_text("# Backend Guide\n\nContent.\n")

        # Compute actual hashes
        h1 = run(["compute", str(f1)], str(tmp_path))["files"][0]["hash"]
        h2 = run(["compute", str(f2)], str(tmp_path))["files"][0]["hash"]

        plan = mb / "generation-plan.md"
        plan.write_text(dedent(f"""\
            ## Metadata

            Generation Base: (pending)
            Generation Commit: (pending)

            ## Files

            | Status | File | Location | Lines | Hash | Source Hash |
            |--------|------|----------|-------|------|-------------|
            | [x] | testing.md | .memory_bank/guides/ | 3 | {h1} | aaa111 |
            | [x] | backend.md | .memory_bank/guides/ | 3 | {h2} | bbb222 |
        """))
        return f1, f2

    def test_detect_no_changes(self, tmp_path):
        self._setup_project(tmp_path)
        out = run(["detect"], str(tmp_path))
        assert out["status"] == "success"
        assert out["summary"]["modified"] == 0
        assert out["summary"]["unchanged"] == 2

    def test_detect_modified_file(self, tmp_path):
        f1, _ = self._setup_project(tmp_path)
        f1.write_text("# Testing Guide\n\nModified content.\n")
        out = run(["detect"], str(tmp_path))
        assert out["summary"]["modified"] == 1
        assert ".memory_bank/guides/testing.md" in out["modified"]

    def test_detect_non_md_files(self, tmp_path):
        """Non-markdown files (e.g. .py) in .claude/ are detected, not reported as missing."""
        mb = tmp_path / ".memory_bank"
        mb.mkdir()
        claude = tmp_path / ".claude"
        skills = claude / "skills"
        skills.mkdir(parents=True)

        py_file = skills / "defer.py"
        py_file.write_text("#!/usr/bin/env python3\nprint('hello')\n")

        h = run(["compute", str(py_file)], str(tmp_path))["files"][0]["hash"]

        plan = mb / "generation-plan.md"
        plan.write_text(dedent(f"""\
            ## Files

            | Status | File | Location | Lines | Hash | Source Hash |
            |--------|------|----------|-------|------|-------------|
            | [x] | defer.py | .claude/skills/ | 2 | {h} | aaa111 |
        """))

        out = run(["detect"], str(tmp_path))
        assert out["status"] == "success"
        assert out["summary"]["missing"] == 0
        assert ".claude/skills/defer.py" in out["unchanged"]

    def test_detect_missing_plan(self, tmp_path):
        out = run(["detect"], str(tmp_path))
        assert out["status"] == "error"


# ============ CLI: merge ============


@pytest.mark.e2e
class TestMergeCLI:
    def test_merge_requires_git(self, tmp_path):
        """Merge needs git to recover base — fails gracefully without it."""
        target = tmp_path / "file.md"
        target.write_text("local content")
        new = tmp_path / "new.md"
        new.write_text("new content")
        out = run(
            ["merge", str(target), "--base-commit", "nonexistent", "--new-file", str(new)],
            str(tmp_path),
        )
        assert out["status"] == "error"

    def test_merge_in_git_repo(self, tmp_path):
        """Full merge test inside a real git repo."""
        tmp = str(tmp_path)
        # Init git repo
        subprocess.run(["git", "init"], cwd=tmp, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp, capture_output=True,
        )

        # Create base version and commit
        f = tmp_path / "doc.md"
        f.write_text("## A\n\nOriginal A.\n\n## B\n\nOriginal B.\n")
        subprocess.run(["git", "add", "."], cwd=tmp, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "base"],
            cwd=tmp, capture_output=True,
        )
        base_hash = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=tmp, capture_output=True, text=True,
        ).stdout.strip()

        # User modifies the file locally
        f.write_text("## A\n\nUser modified A.\n\n## B\n\nOriginal B.\n\n## Custom\n\nUser section.\n")

        # New plugin version
        new_file = tmp_path / "new_version.md"
        new_file.write_text("## A\n\nOriginal A.\n\n## B\n\nPlugin updated B.\n\n## C\n\nNew from plugin.\n")

        out = run(
            ["merge", "doc.md", "--base-commit", base_hash, "--new-file", str(new_file)],
            tmp,
        )
        assert out["status"] == "merged"
        assert "User modified A" in out["merged_content"]
        assert "Plugin updated B" in out["merged_content"]
        assert "Custom" in out["merged_content"]
        assert "New from plugin" in out["merged_content"]

    def test_merge_no_local_changes(self, tmp_path):
        """If local == base, just returns new version."""
        tmp = str(tmp_path)
        subprocess.run(["git", "init"], cwd=tmp, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmp, capture_output=True)

        f = tmp_path / "doc.md"
        f.write_text("## A\n\nContent.\n")
        subprocess.run(["git", "add", "."], cwd=tmp, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp, capture_output=True)
        base = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=tmp, capture_output=True, text=True
        ).stdout.strip()

        new_file = tmp_path / "new.md"
        new_file.write_text("## A\n\nUpdated.\n")

        out = run(["merge", "doc.md", "--base-commit", base, "--new-file", str(new_file)], tmp)
        assert out["status"] == "no_local_changes"
        assert "Updated" in out["merged_content"]


# ============ CLI: commit-generation ============


@pytest.mark.e2e
class TestCommitGenerationCLI:
    def _init_repo(self, tmp_path):
        tmp = str(tmp_path)
        subprocess.run(["git", "init"], cwd=tmp, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmp, capture_output=True)

    def test_simple_commit(self, tmp_path):
        """Without --clean-dir: single commit, base == commit."""
        self._init_repo(tmp_path)
        tmp = str(tmp_path)

        # Create files
        mb = tmp_path / ".memory_bank"
        mb.mkdir()
        (mb / "README.md").write_text("# README\n")
        plan = mb / "generation-plan.md"
        plan.write_text("## Metadata\n\nGeneration Base: (pending)\nGeneration Commit: (pending)\n")

        # Need CLAUDE.md to exist for git add
        (tmp_path / "CLAUDE.md").write_text("# CLAUDE\n")
        (tmp_path / ".claude").mkdir()

        out = run(["commit-generation", "--plugin-version", "1.3.0"], tmp)
        assert out["status"] == "success"
        assert out["generation_base"] == out["generation_commit"]
        assert out["merge_applied"] is False

        # Check metadata was updated in plan
        plan_content = plan.read_text()
        assert out["generation_base"] in plan_content

    def test_commit_with_clean_dir(self, tmp_path):
        """With --clean-dir: two commits if clean differs from current."""
        self._init_repo(tmp_path)
        tmp = str(tmp_path)

        mb = tmp_path / ".memory_bank"
        mb.mkdir()
        guides = mb / "guides"
        guides.mkdir()

        # Current file has merged content
        (guides / "testing.md").write_text("# Testing\n\nPlugin content.\n\n## User Section\n\nCustom.\n")
        plan = mb / "generation-plan.md"
        plan.write_text("## Metadata\n\nGeneration Base: (pending)\nGeneration Commit: (pending)\n")
        (tmp_path / "CLAUDE.md").write_text("# CLAUDE\n")
        (tmp_path / ".claude").mkdir()

        # Clean dir has plugin-only version
        clean = tmp_path / "clean"
        clean_guides = clean / ".memory_bank" / "guides"
        clean_guides.mkdir(parents=True)
        (clean_guides / "testing.md").write_text("# Testing\n\nPlugin content.\n")
        # Copy plan and CLAUDE to clean too
        clean_mb = clean / ".memory_bank"
        (clean_mb / "generation-plan.md").write_text(plan.read_text())
        (clean / "CLAUDE.md").write_text("# CLAUDE\n")

        out = run(["commit-generation", "--plugin-version", "1.3.0", "--clean-dir", str(clean)], tmp)
        assert out["status"] == "success"
        assert out["merge_applied"] is True
        assert out["generation_base"] != out["generation_commit"]
        assert ".memory_bank/guides/testing.md" in out["files_merged"]

        # Verify base commit has clean content
        base_content = subprocess.run(
            ["git", "show", f"{out['generation_base']}:.memory_bank/guides/testing.md"],
            cwd=tmp, capture_output=True, text=True,
        ).stdout
        assert "User Section" not in base_content
        assert "Plugin content" in base_content

        # Verify final commit has merged content
        final_content = (guides / "testing.md").read_text()
        assert "User Section" in final_content

    def test_commit_no_changes(self, tmp_path):
        """Error when nothing to commit."""
        self._init_repo(tmp_path)
        tmp = str(tmp_path)
        # Create and commit files first
        mb = tmp_path / ".memory_bank"
        mb.mkdir()
        (mb / "README.md").write_text("# README\n")
        (tmp_path / "CLAUDE.md").write_text("# CLAUDE\n")
        (tmp_path / ".claude").mkdir()
        subprocess.run(["git", "add", "."], cwd=tmp, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp, capture_output=True)

        # Now try commit-generation with no new changes
        out = run(["commit-generation", "--plugin-version", "1.0.0"], tmp)
        assert out["status"] == "error"


# ============ Metadata helpers ============


class TestMetadataHelpers:
    def test_parse_metadata(self, tmp_path):
        plan = tmp_path / ".memory_bank" / "generation-plan.md"
        plan.parent.mkdir(parents=True)
        plan.write_text(dedent("""\
            ## Metadata

            Generation Base: abc1234
            Generation Commit: def5678
            Generated: 2026-02-20
            Plugin Version: 1.3.0

            ## Files

            | Status | File |
        """))

        # Monkey-patch GENERATION_PLAN
        ns = {}
        exec(compile(SCRIPT.read_text(), str(SCRIPT), "exec"), ns)
        old_plan = ns["GENERATION_PLAN"]
        ns["GENERATION_PLAN"] = plan
        try:
            meta = ns["parse_plan_metadata"]()
        finally:
            ns["GENERATION_PLAN"] = old_plan

        assert meta["Generation Base"] == "abc1234"
        assert meta["Generation Commit"] == "def5678"
        assert meta["Plugin Version"] == "1.3.0"

    def test_update_metadata_existing_key(self, tmp_path):
        plan = tmp_path / "plan.md"
        plan.write_text("## Metadata\n\nGeneration Base: old\nGeneration Commit: old\n\n## Files\n")

        ns = {}
        exec(compile(SCRIPT.read_text(), str(SCRIPT), "exec"), ns)
        old_plan = ns["GENERATION_PLAN"]
        ns["GENERATION_PLAN"] = plan
        try:
            ns["update_plan_metadata"]("Generation Base", "new123")
        finally:
            ns["GENERATION_PLAN"] = old_plan

        content = plan.read_text()
        assert "Generation Base: new123" in content
        assert "Generation Commit: old" in content

    def test_update_metadata_new_key(self, tmp_path):
        plan = tmp_path / "plan.md"
        plan.write_text("## Metadata\n\nGeneration Commit: abc\n\n## Files\n")

        ns = {}
        exec(compile(SCRIPT.read_text(), str(SCRIPT), "exec"), ns)
        old_plan = ns["GENERATION_PLAN"]
        ns["GENERATION_PLAN"] = plan
        try:
            ns["update_plan_metadata"]("Generation Base", "xyz789")
        finally:
            ns["GENERATION_PLAN"] = old_plan

        content = plan.read_text()
        assert "Generation Base: xyz789" in content


# ============ Generation plan parsing ============


class TestGenerationPlan:
    def test_parse_plan_table(self, tmp_path):
        plan = tmp_path / ".memory_bank" / "generation-plan.md"
        plan.parent.mkdir(parents=True)
        plan.write_text(dedent("""\
            ## Files

            | Status | File | Location | Lines | Hash | Source Hash |
            |--------|------|----------|-------|------|-------------|
            | [x] | README.md | .memory_bank/ | 127 | abc123 | def456 |
            | [x] | testing.md | .memory_bank/guides/ | 295 | ghi789 | jkl012 |
            | [ ] | pending.md | .memory_bank/ | ~100 | | |
        """))

        ns = {}
        exec(compile(SCRIPT.read_text(), str(SCRIPT), "exec"), ns)
        old_plan = ns["GENERATION_PLAN"]
        ns["GENERATION_PLAN"] = plan
        try:
            data = ns["parse_generation_plan"]()
        finally:
            ns["GENERATION_PLAN"] = old_plan

        assert ".memory_bank/README.md" in data
        assert data[".memory_bank/README.md"]["hash"] == "abc123"
        assert data[".memory_bank/README.md"]["source_hash"] == "def456"
        assert ".memory_bank/guides/testing.md" in data
        # Pending files ([ ]) should not be in parsed data
        assert ".memory_bank/pending.md" not in data


# ============ CLI: recompute-source-hashes ============


@pytest.mark.e2e
class TestRecomputeSourceHashes:
    def test_creates_json(self, tmp_path):
        """Creates source-hashes.json with correct hashes."""
        tmp = str(tmp_path)
        # Create prompts/
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        p1 = prompts / "CLAUDE.md.prompt"
        p1.write_text("prompt content\n")
        mb_prompts = prompts / "memory_bank"
        mb_prompts.mkdir()
        p2 = mb_prompts / "README.md.prompt"
        p2.write_text("readme prompt\n")

        # Create static/
        static = tmp_path / "static"
        static.mkdir()
        s1 = static / "manifest.yaml"
        s1.write_text("- file: test\n")
        wf = static / "memory_bank" / "workflows"
        wf.mkdir(parents=True)
        s2 = wf / "dev.md"
        s2.write_text("workflow content\n")

        out = run(["recompute-source-hashes", "--plugin-root", tmp], tmp)
        assert out["status"] == "success"
        assert out["files"] == 3  # 2 prompts + 1 static (manifest excluded)

        # Verify JSON file
        json_path = tmp_path / "source-hashes.json"
        assert json_path.exists()
        data = json.loads(json_path.read_text())
        assert "prompts/CLAUDE.md.prompt" in data
        assert "prompts/memory_bank/README.md.prompt" in data
        assert "static/memory_bank/workflows/dev.md" in data

        # Verify hashes are correct (8-char MD5)
        assert len(data["prompts/CLAUDE.md.prompt"]) == 8
        expected_hash = compute_hash(p1)
        assert data["prompts/CLAUDE.md.prompt"] == expected_hash

    def test_excludes_manifest(self, tmp_path):
        """manifest.yaml is not included in source-hashes.json."""
        tmp = str(tmp_path)
        static = tmp_path / "static"
        static.mkdir()
        (static / "manifest.yaml").write_text("manifest\n")
        (static / "file.md").write_text("content\n")

        out = run(["recompute-source-hashes", "--plugin-root", tmp], tmp)
        assert out["files"] == 1

        data = json.loads((tmp_path / "source-hashes.json").read_text())
        assert "static/manifest.yaml" not in data
        assert "static/file.md" in data

    def test_excludes_pycache(self, tmp_path):
        """__pycache__ files are not included."""
        tmp = str(tmp_path)
        static = tmp_path / "static"
        cache = static / "scripts" / "__pycache__"
        cache.mkdir(parents=True)
        (cache / "foo.cpython-314.pyc").write_bytes(b"\x00\x01")
        (static / "scripts" / "real.py").write_text("code\n")

        run(["recompute-source-hashes", "--plugin-root", tmp], tmp)
        data = json.loads((tmp_path / "source-hashes.json").read_text())
        assert not any("__pycache__" in k for k in data)
        assert "static/scripts/real.py" in data


# ============ CLI: update-plan ============


@pytest.mark.e2e
class TestUpdatePlan:
    def _setup_project(self, tmp_path):
        """Create project with generation-plan.md and some generated files."""
        mb = tmp_path / ".memory_bank"
        mb.mkdir()
        guides = mb / "guides"
        guides.mkdir()

        f1 = guides / "testing.md"
        f1.write_text("# Testing Guide\n\nContent.\n")
        f2 = guides / "backend.md"
        f2.write_text("# Backend Guide\n\nContent.\n")

        plan = mb / "generation-plan.md"
        plan.write_text(dedent("""\
            ## Metadata

            Generation Base: (pending)

            ## Files

            | Status | File | Location | Lines | Hash | Source Hash |
            |--------|------|----------|-------|------|-------------|
            | [ ] | testing.md | .memory_bank/guides/ | ~280 | | |
            | [ ] | backend.md | .memory_bank/guides/ | ~450 | | |
        """))

        # Create plugin with source-hashes.json
        plugin = tmp_path / "plugin"
        plugin.mkdir()
        prompts = plugin / "prompts" / "memory_bank" / "guides"
        prompts.mkdir(parents=True)
        (prompts / "testing.md.prompt").write_text("testing prompt\n")
        (prompts / "backend.md.prompt").write_text("backend prompt\n")

        # Generate source-hashes.json
        run(["recompute-source-hashes", "--plugin-root", str(plugin)], str(tmp_path))

        return f1, f2, plan, str(plugin)

    def test_marks_complete(self, tmp_path):
        """[x], hash, source_hash, lines are updated."""
        f1, _, plan, plugin = self._setup_project(tmp_path)
        out = run(
            ["update-plan", ".memory_bank/guides/testing.md", "--plugin-root", plugin],
            str(tmp_path),
        )
        assert out["status"] == "success"
        assert len(out["updated"]) == 1
        assert out["updated"][0]["file"] == ".memory_bank/guides/testing.md"
        assert out["updated"][0]["hash"]
        assert out["updated"][0]["lines"] == 3

        # Verify plan content
        content = plan.read_text()
        assert "[x]" in content
        assert out["updated"][0]["hash"] in content

    def test_multiple_files(self, tmp_path):
        """Multiple files updated in one call."""
        f1, f2, plan, plugin = self._setup_project(tmp_path)
        out = run(
            [
                "update-plan",
                ".memory_bank/guides/testing.md",
                ".memory_bank/guides/backend.md",
                "--plugin-root",
                plugin,
            ],
            str(tmp_path),
        )
        assert out["status"] == "success"
        assert len(out["updated"]) == 2

        content = plan.read_text()
        assert content.count("[x]") == 2

    def test_auto_add_missing_row(self, tmp_path):
        """File not in plan table is auto-added to correct section."""
        mb = tmp_path / ".memory_bank"
        guides = mb / "guides"
        guides.mkdir(parents=True)

        f1 = guides / "testing.md"
        f1.write_text("# Testing Guide\n\nContent.\n")
        f2 = guides / "new-guide.md"
        f2.write_text("# New Guide\n\nBrand new.\n")

        plan = mb / "generation-plan.md"
        plan.write_text(dedent("""\
            ## Metadata

            Generation Base: (pending)

            ## Files

            ### Guides

            | Status | File | Location | Lines | Hash | Source Hash |
            |--------|------|----------|-------|------|-------------|
            | [ ] | testing.md | .memory_bank/guides/ | ~280 | | |
        """))

        plugin = tmp_path / "plugin"
        plugin.mkdir()
        (plugin / "source-hashes.json").write_text("{}\n")

        out = run(
            [
                "update-plan",
                ".memory_bank/guides/testing.md",
                ".memory_bank/guides/new-guide.md",
                "--plugin-root",
                str(plugin),
            ],
            str(tmp_path),
        )
        assert out["status"] == "success"
        assert len(out["updated"]) == 1  # testing.md was updated
        assert len(out["added"]) == 1    # new-guide.md was added
        assert out["added"][0]["file"] == ".memory_bank/guides/new-guide.md"

        content = plan.read_text()
        assert "new-guide.md" in content
        assert content.count("[x]") == 2

    def test_remove_row(self, tmp_path):
        """--remove deletes rows from generation plan."""
        mb = tmp_path / ".memory_bank"
        guides = mb / "guides"
        guides.mkdir(parents=True)

        f1 = guides / "testing.md"
        f1.write_text("# Testing Guide\n\nContent.\n")

        plan = mb / "generation-plan.md"
        plan.write_text(dedent("""\
            ## Files

            | Status | File | Location | Lines | Hash | Source Hash |
            |--------|------|----------|-------|------|-------------|
            | [x] | testing.md | .memory_bank/guides/ | 3 | abc123 | def456 |
            | [x] | obsolete.md | .memory_bank/guides/ | 10 | ghi789 | jkl012 |
        """))

        plugin = tmp_path / "plugin"
        plugin.mkdir()
        (plugin / "source-hashes.json").write_text("{}\n")

        out = run(
            [
                "update-plan",
                ".memory_bank/guides/testing.md",
                "--plugin-root",
                str(plugin),
                "--remove",
                ".memory_bank/guides/obsolete.md",
            ],
            str(tmp_path),
        )
        assert out["status"] == "success"
        assert len(out["removed"]) == 1
        assert out["removed"][0]["file"] == ".memory_bank/guides/obsolete.md"

        content = plan.read_text()
        assert "obsolete.md" not in content
        assert "testing.md" in content

    def test_remove_nonexistent_row(self, tmp_path):
        """--remove for file not in plan produces warning."""
        mb = tmp_path / ".memory_bank"
        mb.mkdir()

        f1 = mb / "README.md"
        f1.write_text("# README\n")

        plan = mb / "generation-plan.md"
        plan.write_text(dedent("""\
            ## Files

            | Status | File | Location | Lines | Hash | Source Hash |
            |--------|------|----------|-------|------|-------------|
            | [ ] | README.md | .memory_bank/ | ~100 | | |
        """))

        plugin = tmp_path / "plugin"
        plugin.mkdir()
        (plugin / "source-hashes.json").write_text("{}\n")

        out = run(
            [
                "update-plan",
                ".memory_bank/README.md",
                "--plugin-root",
                str(plugin),
                "--remove",
                ".memory_bank/guides/nonexistent.md",
            ],
            str(tmp_path),
        )
        assert out["status"] == "success"
        assert any(
            w["warning"] == "Row not found for removal"
            for w in out.get("warnings", [])
        )

    def test_missing_source_hash(self, tmp_path):
        """File with no source hash → warning, empty field."""
        mb = tmp_path / ".memory_bank"
        mb.mkdir()
        f1 = mb / "orphan.md"
        f1.write_text("orphan content\n")

        plan = mb / "generation-plan.md"
        plan.write_text(dedent("""\
            ## Files

            | Status | File | Location | Lines | Hash | Source Hash |
            |--------|------|----------|-------|------|-------------|
            | [ ] | orphan.md | .memory_bank/ | ~100 | | |
        """))

        # Plugin with no matching source
        plugin = tmp_path / "plugin"
        plugin.mkdir()
        (plugin / "source-hashes.json").write_text("{}\n")

        out = run(
            ["update-plan", ".memory_bank/orphan.md", "--plugin-root", str(plugin)],
            str(tmp_path),
        )
        assert out["status"] == "success"
        assert len(out["updated"]) == 1
        assert out["updated"][0]["source_hash"] is None


# ============ compute-source reads from JSON ============


@pytest.mark.e2e
class TestComputeSourceJSON:
    def test_reads_from_json(self, tmp_path):
        """When source-hashes.json exists, uses hash from it."""
        plugin = tmp_path / "plugin"
        prompts = plugin / "prompts"
        prompts.mkdir(parents=True)
        prompt_file = prompts / "CLAUDE.md.prompt"
        prompt_file.write_text("content\n")

        # Create source-hashes.json with a known hash
        hashes = {"prompts/CLAUDE.md.prompt": "fakehash"}
        (plugin / "source-hashes.json").write_text(json.dumps(hashes))

        out = run(
            ["compute-source", "prompts/CLAUDE.md.prompt", "--plugin-root", str(plugin)],
            str(tmp_path),
        )
        assert out["status"] == "success"
        # Should use the JSON hash, not compute from file
        assert out["files"][0]["hash"] == "fakehash"

    def test_fallback_without_json(self, tmp_path):
        """Without source-hashes.json, computes from file."""
        plugin = tmp_path / "plugin"
        prompts = plugin / "prompts"
        prompts.mkdir(parents=True)
        prompt_file = prompts / "CLAUDE.md.prompt"
        prompt_file.write_text("content\n")

        out = run(
            ["compute-source", "prompts/CLAUDE.md.prompt", "--plugin-root", str(plugin)],
            str(tmp_path),
        )
        assert out["status"] == "success"
        # Should compute real hash from file
        expected = compute_hash(prompt_file)
        assert out["files"][0]["hash"] == expected


# ============ detect-source-changes uses JSON ============


@pytest.mark.e2e
class TestDetectSourceChangesJSON:
    def test_uses_json(self, tmp_path):
        """detect-source-changes reads from source-hashes.json when available."""
        # Setup: generation-plan.md with a stored source hash
        mb = tmp_path / ".memory_bank"
        mb.mkdir()
        guides = mb / "guides"
        guides.mkdir()
        (guides / "testing.md").write_text("content\n")

        plan = mb / "generation-plan.md"
        plan.write_text(dedent("""\
            ## Files

            | Status | File | Location | Lines | Hash | Source Hash |
            |--------|------|----------|-------|------|-------------|
            | [x] | testing.md | .memory_bank/guides/ | 1 | abc123 | original |
        """))

        # Setup plugin with source-hashes.json containing a different hash
        plugin = tmp_path / "plugin"
        prompts = plugin / "prompts" / "memory_bank" / "guides"
        prompts.mkdir(parents=True)
        (prompts / "testing.md.prompt").write_text("prompt\n")

        hashes = {"prompts/memory_bank/guides/testing.md.prompt": "changed!"}
        (plugin / "source-hashes.json").write_text(json.dumps(hashes))

        out = run(
            ["detect-source-changes", "--plugin-root", str(plugin)],
            str(tmp_path),
        )
        assert out["status"] == "success"
        assert len(out["changed"]) == 1
        assert out["changed"][0]["current_hash"] == "changed!"
        assert out["changed"][0]["stored_hash"] == "original"


# ============ Conditional Evaluator ============


class TestEvaluateConditional:
    """Test the conditional expression evaluator."""

    @pytest.mark.parametrize(
        "expr, analysis, expected",
        [
            # Null / empty → always true
            pytest.param(None, {}, True, id="null_is_true"),
            pytest.param("null", {}, True, id="null_string_is_true"),
            pytest.param("", {}, True, id="empty_string_is_true"),
            # Simple boolean fields
            pytest.param("has_frontend", {"has_frontend": True}, True, id="simple_bool_true"),
            pytest.param("has_frontend", {"has_frontend": False}, False, id="simple_bool_false"),
            pytest.param("has_frontend", {}, False, id="missing_field_is_false"),
            # Equality operators
            pytest.param("backend_language == 'Python'", {"backend_language": "Python"}, True, id="equality_match"),
            pytest.param("backend_language == 'Python'", {"backend_language": "Ruby"}, False, id="equality_no_match"),
            pytest.param("backend_language == 'Python'", {"backend_language": "python"}, True, id="equality_case_insensitive"),
            pytest.param('backend_framework == "Django"', {"backend_framework": "Django"}, True, id="equality_double_quotes"),
            # Not operator
            pytest.param("!has_database", {"has_database": False}, True, id="not_false_is_true"),
            pytest.param("!has_database", {"has_database": True}, False, id="not_true_is_false"),
            pytest.param("!nonexistent", {}, True, id="not_missing_field"),
            # And operator
            pytest.param("has_frontend && has_tests", {"has_frontend": True, "has_tests": True}, True, id="and_both_true"),
            pytest.param("has_frontend && has_tests", {"has_frontend": True, "has_tests": False}, False, id="and_one_false"),
            # Or operator
            pytest.param("has_frontend || backend_language == 'TypeScript'", {"has_frontend": False, "backend_language": "TypeScript"}, True, id="or_second_true"),
            pytest.param("has_frontend || backend_language == 'TypeScript'", {"has_frontend": False, "backend_language": "Python"}, False, id="or_both_false"),
            # Complex expression
            pytest.param("has_frontend && has_tests", {"has_frontend": True, "has_tests": True, "backend_language": "Python"}, True, id="complex_and"),
            # String field as boolean
            pytest.param("backend_language", {"backend_language": "Python"}, True, id="string_truthy"),
            pytest.param("backend_language", {"backend_language": ""}, False, id="string_empty_falsy"),
            # None value as boolean
            pytest.param("some_field", {"some_field": None}, False, id="none_value_falsy"),
            # Int value as boolean
            pytest.param("count", {"count": 5}, True, id="int_truthy"),
            pytest.param("count", {"count": 0}, False, id="int_zero_falsy"),
        ],
    )
    def test_evaluate(self, expr, analysis, expected):
        assert evaluate_conditional(expr, analysis) is expected


# ============ Flatten Analysis ============

flatten_analysis = _ns["flatten_analysis"]


class TestFlattenAnalysis:
    """Test flattening of nested project-analysis.json format."""

    NESTED = {
        "status": "success",
        "data": {
            "project_name": "testproject",
            "has_multiple_backends": False,
            "backend": {
                "framework": "FastAPI",
                "version": "0.100",
                "language": "Python",
                "has_backend": True,
            },
            "frontend": {
                "framework": "React",
                "version": "19.0",
                "has_frontend": True,
            },
            "database": {"primary": "PostgreSQL", "orm": "SQLAlchemy"},
            "testing": {"frameworks": ["pytest"], "has_tests": True, "has_e2e_tests": False},
            "structure": {
                "is_monorepo": True,
                "has_docker": True,
                "has_ci_cd": False,
            },
        },
    }

    def test_flattens_backend_fields(self):
        flat = flatten_analysis(self.NESTED)
        assert flat["has_backend"] is True
        assert flat["backend_framework"] == "FastAPI"
        assert flat["backend_language"] == "Python"

    def test_flattens_frontend_fields(self):
        flat = flatten_analysis(self.NESTED)
        assert flat["has_frontend"] is True
        assert flat["frontend_framework"] == "React"

    def test_derives_has_database(self):
        flat = flatten_analysis(self.NESTED)
        assert flat["has_database"] is True

    def test_no_database(self):
        raw = {"data": {"database": {"primary": None}}}
        flat = flatten_analysis(raw)
        assert flat["has_database"] is False

    def test_flattens_testing(self):
        flat = flatten_analysis(self.NESTED)
        assert flat["has_tests"] is True
        assert flat["has_e2e_tests"] is False

    def test_flattens_structure(self):
        flat = flatten_analysis(self.NESTED)
        assert flat["is_monorepo"] is True
        assert flat["has_docker"] is True
        assert flat["has_ci"] is False

    def test_preserves_top_level_scalars(self):
        flat = flatten_analysis(self.NESTED)
        assert flat["project_name"] == "testproject"
        assert flat["has_multiple_backends"] is False

    def test_already_flat_passthrough(self):
        flat_input = {"has_backend": True, "has_frontend": False, "backend_language": "Python"}
        assert flatten_analysis(flat_input) == flat_input

    def test_conditionals_work_with_nested(self):
        """End-to-end: conditionals evaluate correctly against nested format."""
        flat = flatten_analysis(self.NESTED)
        assert evaluate_conditional("has_backend", flat) is True
        assert evaluate_conditional("has_frontend", flat) is True
        assert evaluate_conditional("has_database", flat) is True
        assert evaluate_conditional("backend_language == 'Python'", flat) is True
        assert evaluate_conditional("frontend_framework == 'React'", flat) is True
        assert evaluate_conditional("is_monorepo", flat) is True
        assert evaluate_conditional("!has_ci", flat) is True
        assert evaluate_conditional("has_frontend && has_tests", flat) is True


# ============ Frontmatter Parser ============


class TestParsePromptFrontmatter:
    def test_basic_frontmatter(self, tmp_path):
        f = tmp_path / "test.prompt"
        f.write_text(dedent("""\
            ---
            file: testing.md
            target_path: .memory_bank/guides/
            priority: 15
            dependencies: []
            conditional: null
            ---

            # Generation Instructions
        """))
        result = parse_prompt_frontmatter(f)
        assert result is not None
        assert result["file"] == "testing.md"
        assert result["target_path"] == ".memory_bank/guides/"
        assert result["priority"] == 15
        assert result["conditional"] is None
        assert result["dependencies"] == []

    def test_quoted_conditional(self, tmp_path):
        f = tmp_path / "test.prompt"
        f.write_text(dedent("""\
            ---
            file: visual-design.md
            target_path: .memory_bank/guides/
            priority: 16
            conditional: "has_frontend"
            ---

            Content.
        """))
        result = parse_prompt_frontmatter(f)
        assert result["conditional"] == "has_frontend"

    def test_no_frontmatter(self, tmp_path):
        f = tmp_path / "test.prompt"
        f.write_text("Just content, no frontmatter.\n")
        assert parse_prompt_frontmatter(f) is None

    def test_invalid_frontmatter(self, tmp_path):
        f = tmp_path / "test.prompt"
        f.write_text("---\nno_file_field: true\n---\nContent.\n")
        assert parse_prompt_frontmatter(f) is None

    def test_missing_file(self):
        assert parse_prompt_frontmatter(Path("/nonexistent/file.prompt")) is None

    def test_unclosed_frontmatter(self, tmp_path):
        """Frontmatter starts with --- but has no closing ---."""
        f = tmp_path / "test.prompt"
        f.write_text("---\nfile: test.md\ntarget_path: ./\npriority: 1\n")
        assert parse_prompt_frontmatter(f) is None


# ============ Manifest Parser ============


class TestParseManifest:
    def test_basic_manifest(self, tmp_path):
        f = tmp_path / "manifest.yaml"
        f.write_text(dedent("""\
            files:
              - source: memory_bank/workflows/index.md
                target: .memory_bank/workflows/index.md
                conditional: null

              - source: agents/test-runner.md
                target: .claude/agents/test-runner.md
                conditional: null
        """))
        entries = parse_manifest(f)
        assert len(entries) == 2
        assert entries[0]["source"] == "memory_bank/workflows/index.md"
        assert entries[0]["target"] == ".memory_bank/workflows/index.md"
        assert entries[0]["conditional"] is None
        assert entries[1]["source"] == "agents/test-runner.md"

    def test_conditional_expression(self, tmp_path):
        f = tmp_path / "manifest.yaml"
        f.write_text(dedent("""\
            files:
              - source: agents/design-reviewer.md
                target: .claude/agents/design-reviewer.md
                conditional: "has_frontend"

              - source: review/python.md
                target: .memory_bank/workflows/review/python.md
                conditional: "backend_language == 'Python'"
        """))
        entries = parse_manifest(f)
        assert len(entries) == 2
        assert entries[0]["conditional"] == "has_frontend"
        assert entries[1]["conditional"] == "backend_language == 'Python'"

    def test_missing_manifest(self):
        entries = parse_manifest(Path("/nonexistent/manifest.yaml"))
        assert entries == []

    def test_comments_between_entries(self, tmp_path):
        f = tmp_path / "manifest.yaml"
        f.write_text(dedent("""\
            files:
              - source: file1.md
                target: .memory_bank/file1.md
                conditional: null

              # This is a comment
              - source: file2.md
                target: .memory_bank/file2.md
                conditional: null
        """))
        entries = parse_manifest(f)
        assert len(entries) == 2

    def test_empty_manifest(self, tmp_path):
        f = tmp_path / "manifest.yaml"
        f.write_text("files:\n")
        entries = parse_manifest(f)
        assert entries == []

    def test_single_quoted_conditional(self, tmp_path):
        f = tmp_path / "manifest.yaml"
        f.write_text(dedent("""\
            files:
              - source: agents/design.md
                target: .claude/agents/design.md
                conditional: 'has_frontend'
        """))
        entries = parse_manifest(f)
        assert len(entries) == 1
        assert entries[0]["conditional"] == "has_frontend"

    def test_bare_conditional(self, tmp_path):
        """Unquoted conditional value."""
        f = tmp_path / "manifest.yaml"
        f.write_text(dedent("""\
            files:
              - source: agents/design.md
                target: .claude/agents/design.md
                conditional: has_frontend
        """))
        entries = parse_manifest(f)
        assert len(entries) == 1
        assert entries[0]["conditional"] == "has_frontend"

    def test_last_entry_no_conditional_no_trailing_blank(self, tmp_path):
        """Last entry without conditional and no trailing newline."""
        f = tmp_path / "manifest.yaml"
        # No trailing blank line — relies on EOF flush
        f.write_text("files:\n  - source: f.md\n    target: .mb/f.md")
        entries = parse_manifest(f)
        assert len(entries) == 1
        assert entries[0]["conditional"] is None


# ============ Classify Static Files ============


class TestClassifyStaticFiles:
    def test_new_file(self):
        """File in manifest but not in project → new."""
        manifest = [{"source": "workflows/new.md", "target": ".memory_bank/workflows/new.md",
                      "conditional": None}]
        result = classify_static_files(
            manifest, Path("/plugin"), {}, {"has_frontend": True}, {}
        )
        assert len(result["new"]) == 1
        assert result["new"][0]["target"] == ".memory_bank/workflows/new.md"

    def test_skipped_conditional(self):
        """File with unmet conditional → skipped."""
        manifest = [{"source": "agents/design.md", "target": ".claude/agents/design.md",
                      "conditional": "has_frontend"}]
        result = classify_static_files(
            manifest, Path("/plugin"), {}, {"has_frontend": False}, {}
        )
        assert len(result["skipped_conditional"]) == 1

    def test_up_to_date(self, tmp_path):
        """File exists, no local changes, no plugin changes → up_to_date."""
        target = tmp_path / ".memory_bank" / "file.md"
        target.parent.mkdir(parents=True)
        target.write_text("content\n")
        h = compute_hash(target)

        manifest = [{"source": "memory_bank/file.md",
                      "target": str(target), "conditional": None}]
        plan = {str(target): {"hash": h, "source_hash": "src123"}}
        source_hashes = {"static/memory_bank/file.md": "src123"}

        result = classify_static_files(
            manifest, tmp_path, plan, {}, source_hashes
        )
        assert len(result["up_to_date"]) == 1

    def test_safe_overwrite(self, tmp_path):
        """File exists, no local changes, plugin updated → safe_overwrite."""
        target = tmp_path / ".memory_bank" / "file.md"
        target.parent.mkdir(parents=True)
        target.write_text("content\n")
        h = compute_hash(target)

        manifest = [{"source": "memory_bank/file.md",
                      "target": str(target), "conditional": None}]
        plan = {str(target): {"hash": h, "source_hash": "old_src"}}
        source_hashes = {"static/memory_bank/file.md": "new_src"}

        result = classify_static_files(
            manifest, tmp_path, plan, {}, source_hashes
        )
        assert len(result["safe_overwrite"]) == 1

    def test_local_only(self, tmp_path):
        """File exists, locally modified, no plugin changes → local_only."""
        target = tmp_path / ".memory_bank" / "file.md"
        target.parent.mkdir(parents=True)
        target.write_text("modified content\n")

        manifest = [{"source": "memory_bank/file.md",
                      "target": str(target), "conditional": None}]
        plan = {str(target): {"hash": "different_hash", "source_hash": "src123"}}
        source_hashes = {"static/memory_bank/file.md": "src123"}

        result = classify_static_files(
            manifest, tmp_path, plan, {}, source_hashes
        )
        assert len(result["local_only"]) == 1

    def test_merge_needed(self, tmp_path):
        """File exists, locally modified AND plugin updated → merge_needed."""
        target = tmp_path / ".memory_bank" / "file.md"
        target.parent.mkdir(parents=True)
        target.write_text("modified content\n")

        manifest = [{"source": "memory_bank/file.md",
                      "target": str(target), "conditional": None}]
        plan = {str(target): {"hash": "different_hash", "source_hash": "old_src"}}
        source_hashes = {"static/memory_bank/file.md": "new_src"}

        result = classify_static_files(
            manifest, tmp_path, plan, {}, source_hashes
        )
        assert len(result["merge_needed"]) == 1

    def test_source_hash_fallback_to_file(self, tmp_path):
        """When source_hashes is None, compute hash from plugin file."""
        # Create plugin source file
        plugin = tmp_path / "plugin"
        src = plugin / "static" / "memory_bank"
        src.mkdir(parents=True)
        (src / "file.md").write_text("plugin content\n")
        compute_hash(src / "file.md")  # ensure file is hashable

        target = tmp_path / ".memory_bank" / "file.md"
        target.parent.mkdir(parents=True)
        target.write_text("plugin content\n")
        h = compute_hash(target)

        manifest = [{"source": "memory_bank/file.md",
                      "target": str(target), "conditional": None}]
        # stored source_hash differs from actual → plugin_updated=True
        plan = {str(target): {"hash": h, "source_hash": "old_hash"}}

        result = classify_static_files(
            manifest, plugin, plan, {}, source_hashes=None
        )
        assert len(result["safe_overwrite"]) == 1

    def test_source_hash_fallback_file_missing(self, tmp_path):
        """When source_hashes is None and plugin file doesn't exist → no update detected."""
        plugin = tmp_path / "plugin"
        (plugin / "static").mkdir(parents=True)
        # No actual source file

        target = tmp_path / ".memory_bank" / "file.md"
        target.parent.mkdir(parents=True)
        target.write_text("content\n")
        h = compute_hash(target)

        manifest = [{"source": "memory_bank/file.md",
                      "target": str(target), "conditional": None}]
        plan = {str(target): {"hash": h, "source_hash": "old_hash"}}

        result = classify_static_files(
            manifest, plugin, plan, {}, source_hashes=None
        )
        # Can't compute current source hash, plugin_updated=False
        assert len(result["up_to_date"]) == 1


# ============ Tech Stack Comparison ============


class TestCompareTechStacks:
    def test_framework_change_high_impact(self):
        old = {"backend_framework": "Django"}
        new = {"backend_framework": "FastAPI"}
        result = compare_tech_stacks(old, new)
        assert len(result["high"]) == 1
        assert result["high"][0]["reason"] == "framework_change"

    def test_framework_added_medium_impact(self):
        old = {"frontend_framework": None}
        new = {"frontend_framework": "React"}
        result = compare_tech_stacks(old, new)
        assert len(result["medium"]) == 1
        assert result["medium"][0]["reason"] == "framework_added"

    def test_major_version_change(self):
        old = {"backend_framework_version": "4.2"}
        new = {"backend_framework_version": "5.0"}
        result = compare_tech_stacks(old, new)
        assert len(result["medium"]) == 1
        assert result["medium"][0]["reason"] == "major_version_change"

    def test_minor_version_change(self):
        old = {"backend_framework_version": "4.2"}
        new = {"backend_framework_version": "4.5"}
        result = compare_tech_stacks(old, new)
        assert len(result["low"]) == 1
        assert result["low"][0]["reason"] == "minor_version_change"

    def test_capability_added(self):
        old = {"has_tests": False}
        new = {"has_tests": True}
        result = compare_tech_stacks(old, new)
        assert any(c["reason"] == "capability_added" for c in result["medium"])

    def test_no_changes(self):
        stack = {"backend_framework": "Django", "has_frontend": True}
        result = compare_tech_stacks(stack, stack)
        assert result == {"high": [], "medium": [], "low": []}


# ============ CLI: pre-update ============


@pytest.mark.e2e
class TestPreUpdateCLI:
    def _setup_project(self, tmp_path):
        """Create a project with analysis + plan + plugin."""
        mb = tmp_path / ".memory_bank"
        mb.mkdir()
        guides = mb / "guides"
        guides.mkdir()

        f1 = guides / "testing.md"
        f1.write_text("# Testing Guide\n\nContent.\n")
        h1 = compute_hash(f1)

        analysis = {
            "has_frontend": True, "has_backend": True,
            "has_tests": True, "has_database": False,
            "backend_language": "Python", "backend_framework": "Django"
        }
        (mb / "project-analysis.json").write_text(
            json.dumps(analysis, indent=2)
        )

        plan = mb / "generation-plan.md"
        plan.write_text(dedent(f"""\
            ## Metadata

            Generation Base: (pending)

            ## Files

            | Status | File | Location | Lines | Hash | Source Hash |
            |--------|------|----------|-------|------|-------------|
            | [x] | testing.md | .memory_bank/guides/ | 3 | {h1} | aaa111 |
        """))

        # Create plugin
        plugin = tmp_path / "plugin"
        (plugin / "prompts" / "memory_bank" / "guides").mkdir(parents=True)
        (plugin / "static").mkdir(parents=True)

        prompt = plugin / "prompts" / "memory_bank" / "guides" / "testing.md.prompt"
        prompt.write_text("---\nfile: testing.md\ntarget_path: .memory_bank/guides/\npriority: 15\nconditional: null\n---\nInstructions.\n")

        manifest = plugin / "static" / "manifest.yaml"
        manifest.write_text("files:\n")

        # Generate source-hashes.json
        run(["recompute-source-hashes", "--plugin-root", str(plugin)], str(tmp_path))

        return str(plugin)

    def test_basic_pre_update(self, tmp_path):
        plugin = self._setup_project(tmp_path)
        out = run(["pre-update", "--plugin-root", plugin], str(tmp_path))
        assert out["status"] == "success"
        assert "local_changes" in out
        assert "source_changes" in out
        assert "new_prompts" in out
        assert "static_files" in out
        assert "summary" in out

    def test_pre_update_with_new_analysis(self, tmp_path):
        plugin = self._setup_project(tmp_path)

        new_analysis = {"has_frontend": True, "has_backend": True,
                        "has_tests": True, "has_database": True,
                        "backend_language": "Python",
                        "backend_framework": "FastAPI"}
        new_path = tmp_path / "new-analysis.json"
        new_path.write_text(json.dumps(new_analysis))

        out = run(["pre-update", "--plugin-root", plugin,
                   "--new-analysis", str(new_path)], str(tmp_path))
        assert out["status"] == "success"
        assert out["tech_stack_diff"] is not None
        assert len(out["tech_stack_diff"]["high"]) >= 1

    def test_pre_update_no_analysis(self, tmp_path):
        """Fails gracefully when project-analysis.json missing."""
        mb = tmp_path / ".memory_bank"
        mb.mkdir()
        (mb / "generation-plan.md").write_text("## Files\n")
        out = run(["pre-update", "--plugin-root", str(tmp_path)], str(tmp_path))
        assert out["status"] == "error"


# ============ CLI: copy-static ============


@pytest.mark.e2e
class TestCopyStaticCLI:
    def _setup(self, tmp_path):
        """Create plugin with manifest + project with analysis."""
        mb = tmp_path / ".memory_bank"
        mb.mkdir()
        (mb / "project-analysis.json").write_text(
            json.dumps({"has_frontend": True, "has_backend": True,
                         "backend_language": "Python"})
        )
        (mb / "generation-plan.md").write_text(
            "## Files\n\n| Status | File | Location | Lines | Hash | Source Hash |\n"
        )

        plugin = tmp_path / "plugin"
        static = plugin / "static"
        wf = static / "memory_bank" / "workflows"
        wf.mkdir(parents=True)
        (wf / "dev.md").write_text("# Dev Workflow\n\nContent.\n")
        (wf / "test.md").write_text("# Test Workflow\n\nContent.\n")

        agents = static / "agents"
        agents.mkdir(parents=True)
        (agents / "design.md").write_text("# Design Agent\n")

        manifest = static / "manifest.yaml"
        manifest.write_text(dedent("""\
            files:
              - source: memory_bank/workflows/dev.md
                target: .memory_bank/workflows/dev.md
                conditional: null

              - source: memory_bank/workflows/test.md
                target: .memory_bank/workflows/test.md
                conditional: null

              - source: agents/design.md
                target: .claude/agents/design.md
                conditional: "has_frontend"
        """))

        run(["recompute-source-hashes", "--plugin-root", str(plugin)], str(tmp_path))
        return str(plugin)

    def test_copy_new_files(self, tmp_path):
        """Files not in project are copied as new."""
        plugin = self._setup(tmp_path)
        out = run(["copy-static", "--plugin-root", plugin], str(tmp_path))
        assert out["status"] == "success"
        assert out["summary"]["copied"] >= 2

        # Verify files were written
        assert (tmp_path / ".memory_bank" / "workflows" / "dev.md").exists()
        assert (tmp_path / ".memory_bank" / "workflows" / "test.md").exists()
        assert (tmp_path / ".claude" / "agents" / "design.md").exists()

    def test_copy_with_clean_dir(self, tmp_path):
        """Clean versions saved when --clean-dir specified."""
        plugin = self._setup(tmp_path)
        clean = tmp_path / "clean"
        out = run(["copy-static", "--plugin-root", plugin,
                   "--clean-dir", str(clean)], str(tmp_path))
        assert out["status"] == "success"
        assert (clean / ".memory_bank" / "workflows" / "dev.md").exists()

    def test_conditional_filtering(self, tmp_path):
        """Files with unmet conditionals are skipped."""
        mb = tmp_path / ".memory_bank"
        mb.mkdir()
        (mb / "project-analysis.json").write_text(
            json.dumps({"has_frontend": False, "has_backend": True,
                         "backend_language": "Python"})
        )
        (mb / "generation-plan.md").write_text("## Files\n")

        # Create plugin inline (can't reuse _setup which creates .memory_bank)
        plugin = tmp_path / "plugin"
        static = plugin / "static"
        agents = static / "agents"
        agents.mkdir(parents=True)
        (agents / "design.md").write_text("# Design Agent\n")

        manifest = static / "manifest.yaml"
        manifest.write_text(dedent("""\
            files:
              - source: agents/design.md
                target: .claude/agents/design.md
                conditional: "has_frontend"
        """))

        run(["recompute-source-hashes", "--plugin-root", str(plugin)], str(tmp_path))
        out = run(["copy-static", "--plugin-root", str(plugin)], str(tmp_path))
        assert out["status"] == "success"
        # design.md should be skipped (has_frontend=False)
        assert any(
            s["reason"] == "condition_false"
            for s in out["skipped"]
        )

    def test_no_analysis(self, tmp_path):
        """Fails gracefully when project-analysis.json missing."""
        (tmp_path / ".memory_bank").mkdir()
        out = run(["copy-static", "--plugin-root", str(tmp_path)], str(tmp_path))
        assert out["status"] == "error"


# ============ CLI: merge --write ============


@pytest.mark.e2e
class TestMergeWriteFlag:
    def test_merge_write_no_conflicts(self, tmp_path):
        """--write writes merged content when no conflicts."""
        tmp = str(tmp_path)
        subprocess.run(["git", "init"], cwd=tmp, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"],
                       cwd=tmp, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"],
                       cwd=tmp, capture_output=True)

        f = tmp_path / "doc.md"
        f.write_text("## A\n\nOriginal A.\n\n## B\n\nOriginal B.\n")
        subprocess.run(["git", "add", "."], cwd=tmp, capture_output=True)
        subprocess.run(["git", "commit", "-m", "base"],
                       cwd=tmp, capture_output=True)
        base = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=tmp, capture_output=True, text=True
        ).stdout.strip()

        # User modifies locally
        f.write_text("## A\n\nUser modified A.\n\n## B\n\nOriginal B.\n")

        # New plugin version
        new_file = tmp_path / "new.md"
        new_file.write_text("## A\n\nOriginal A.\n\n## B\n\nPlugin updated B.\n")

        out = run(
            ["merge", "doc.md", "--base-commit", base,
             "--new-file", str(new_file), "--write"],
            tmp,
        )
        assert out["status"] == "merged"
        assert out["written"] is True

        # Verify file was written with correct merge
        content = f.read_text()
        assert "User modified A" in content
        assert "Plugin updated B" in content
        assert "Original A" not in content
        assert "Original B" not in content

    def test_merge_write_with_conflicts_does_not_write(self, tmp_path):
        """--write does NOT write when conflicts exist."""
        tmp = str(tmp_path)
        subprocess.run(["git", "init"], cwd=tmp, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"],
                       cwd=tmp, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"],
                       cwd=tmp, capture_output=True)

        f = tmp_path / "doc.md"
        f.write_text("## A\n\nOriginal.\n")
        subprocess.run(["git", "add", "."], cwd=tmp, capture_output=True)
        subprocess.run(["git", "commit", "-m", "base"],
                       cwd=tmp, capture_output=True)
        base = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=tmp, capture_output=True, text=True
        ).stdout.strip()

        f.write_text("## A\n\nUser version.\n")

        new_file = tmp_path / "new.md"
        new_file.write_text("## A\n\nPlugin version.\n")

        out = run(
            ["merge", "doc.md", "--base-commit", base,
             "--new-file", str(new_file), "--write"],
            tmp,
        )
        assert out["status"] == "conflicts"
        assert out["written"] is False

    def test_merge_no_local_changes_with_write(self, tmp_path):
        """--write writes new content when no local changes."""
        tmp = str(tmp_path)
        subprocess.run(["git", "init"], cwd=tmp, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"],
                       cwd=tmp, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"],
                       cwd=tmp, capture_output=True)

        f = tmp_path / "doc.md"
        f.write_text("## A\n\nContent.\n")
        subprocess.run(["git", "add", "."], cwd=tmp, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"],
                       cwd=tmp, capture_output=True)
        base = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=tmp, capture_output=True, text=True
        ).stdout.strip()

        new_file = tmp_path / "new.md"
        new_file.write_text("## A\n\nUpdated.\n")

        out = run(
            ["merge", "doc.md", "--base-commit", base,
             "--new-file", str(new_file), "--write"],
            tmp,
        )
        assert out["status"] == "no_local_changes"
        assert out["written"] is True
        assert "Updated" in f.read_text()


# ============ Real manifest parsing ============


class TestRealManifest:
    """Test parsing the actual project manifest.yaml."""

    def test_parse_real_manifest(self):
        manifest_path = (
            Path(__file__).resolve().parent.parent
            / "static" / "manifest.yaml"
        )
        if not manifest_path.exists():
            return  # Skip if not in project

        entries = parse_manifest(manifest_path)
        assert len(entries) > 30  # We know there are 40+ entries
        # All entries should have source and target
        for entry in entries:
            assert "source" in entry
            assert "target" in entry
            assert "conditional" in entry


# ============ Helper: patch module globals for unit tests ============


@pytest.fixture()
def patch_globals(monkeypatch, tmp_path):
    """Fixture that patches _ns globals and cwd for direct function calls.

    Returns a callable: call ``patch_globals(directory)`` to set cwd + globals.
    """
    def _apply(tmp: str | Path):
        monkeypatch.chdir(tmp)
        monkeypatch.setitem(_ns, "MEMORY_BANK_DIR", Path(".memory_bank"))
        monkeypatch.setitem(_ns, "GENERATION_PLAN", Path(".memory_bank") / "generation-plan.md")
        monkeypatch.setitem(_ns, "CLAUDE_DIR", Path(".claude"))
    return _apply


def _git_init(tmp: str) -> str:
    """Init git repo and return first commit hash."""
    subprocess.run(["git", "init"], cwd=tmp, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp, capture_output=True)


def _git_commit(tmp: str, msg: str = "init") -> str:
    """Stage all and commit, return hash."""
    subprocess.run(["git", "add", "."], cwd=tmp, capture_output=True)
    subprocess.run(["git", "commit", "-m", msg], cwd=tmp, capture_output=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp, capture_output=True, text=True
    ).stdout.strip()


# ============ Unit: detect_obsolete_files ============


class TestDetectObsoleteFiles:
    def test_finds_obsolete(self, tmp_path):
        """File in plan but no longer in plugin prompts or manifest."""
        plugin = tmp_path / "plugin"
        (plugin / "prompts" / "memory_bank").mkdir(parents=True)
        # No testing.md.prompt exists
        plan_data = {".memory_bank/guides/testing.md": {"hash": "abc"}}
        result = detect_obsolete_files(
            plugin, plan_data, all_prompts=[], manifest=[], analysis={}
        )
        assert len(result) == 1
        assert result[0]["target"] == ".memory_bank/guides/testing.md"

    def test_no_obsolete_when_prompt_exists(self, tmp_path):
        """File in plan with matching prompt → not obsolete."""
        plugin = tmp_path / "plugin"
        prompts = plugin / "prompts" / "memory_bank" / "guides"
        prompts.mkdir(parents=True)
        (prompts / "testing.md.prompt").write_text("---\nfile: testing.md\n---\n")

        plan_data = {".memory_bank/guides/testing.md": {"hash": "abc"}}
        all_prompts = [{"target": ".memory_bank/guides/testing.md", "applies": True}]
        result = detect_obsolete_files(
            plugin, plan_data, all_prompts, manifest=[], analysis={}
        )
        assert len(result) == 0

    def test_no_obsolete_when_in_manifest(self, tmp_path):
        """File in plan with matching manifest entry → not obsolete."""
        plugin = tmp_path / "plugin"
        plugin.mkdir(parents=True)

        plan_data = {".memory_bank/workflows/dev.md": {"hash": "abc"}}
        manifest = [{"source": "memory_bank/workflows/dev.md",
                     "target": ".memory_bank/workflows/dev.md",
                     "conditional": None}]
        result = detect_obsolete_files(
            plugin, plan_data, all_prompts=[], manifest=manifest, analysis={}
        )
        assert len(result) == 0


# ============ Unit: load_project_analysis ============


class TestLoadProjectAnalysis:
    def test_loads_valid(self, tmp_path, patch_globals):
        patch_globals(tmp_path)
        mb = tmp_path / ".memory_bank"
        mb.mkdir()
        (mb / "project-analysis.json").write_text('{"has_frontend": true}')
        result = load_project_analysis()
        assert result == {"has_frontend": True}

    def test_returns_none_if_missing(self, tmp_path, patch_globals):
        patch_globals(tmp_path)
        (tmp_path / ".memory_bank").mkdir()
        result = load_project_analysis()
        assert result is None

    def test_returns_none_on_invalid_json(self, tmp_path, patch_globals):
        patch_globals(tmp_path)
        mb = tmp_path / ".memory_bank"
        mb.mkdir()
        (mb / "project-analysis.json").write_text("not json!")
        result = load_project_analysis()
        assert result is None


# ============ Unit: parse_manifest conditional default ============


class TestParseManifestConditionalDefault:
    def test_missing_conditional_defaults_to_none(self, tmp_path):
        """Entries without conditional: line get conditional=None."""
        f = tmp_path / "manifest.yaml"
        f.write_text(dedent("""\
            files:
              - source: file1.md
                target: .memory_bank/file1.md
        """))
        entries = parse_manifest(f)
        assert len(entries) == 1
        assert entries[0]["conditional"] is None

    def test_mixed_conditional_and_no_conditional(self, tmp_path):
        """Some entries have conditional, some don't."""
        f = tmp_path / "manifest.yaml"
        f.write_text(dedent("""\
            files:
              - source: file1.md
                target: .memory_bank/file1.md

              - source: file2.md
                target: .memory_bank/file2.md
                conditional: "has_frontend"
        """))
        entries = parse_manifest(f)
        assert len(entries) == 2
        assert entries[0]["conditional"] is None
        assert entries[1]["conditional"] == "has_frontend"

    def test_no_conditional_between_entries(self, tmp_path):
        """Entry without conditional followed by another entry."""
        f = tmp_path / "manifest.yaml"
        f.write_text(dedent("""\
            files:
              - source: a.md
                target: .mb/a.md
              - source: b.md
                target: .mb/b.md
                conditional: null
        """))
        entries = parse_manifest(f)
        assert len(entries) == 2
        assert entries[0]["conditional"] is None
        assert entries[1]["conditional"] is None


# ============ Unit: cmd_merge (direct call, not subprocess) ============


class TestCmdMergeUnit:
    def test_write_no_conflicts(self, tmp_path, monkeypatch):
        """--write writes merged content when merge succeeds."""
        _git_init(str(tmp_path))
        target = tmp_path / "doc.md"
        target.write_text("## A\n\nOriginal A.\n\n## B\n\nOriginal B.\n")
        base = _git_commit(str(tmp_path), "base")

        target.write_text("## A\n\nUser modified A.\n\n## B\n\nOriginal B.\n")
        new_file = tmp_path / "new.md"
        new_file.write_text("## A\n\nOriginal A.\n\n## B\n\nPlugin updated B.\n")

        monkeypatch.chdir(tmp_path)
        result = cmd_merge("doc.md", base, str(new_file), write=True)

        assert result["status"] == "merged"
        assert result["written"] is True
        content = target.read_text()
        assert "User modified A" in content
        assert "Plugin updated B" in content
        assert "Original A" not in content
        assert "Original B" not in content

    def test_write_with_conflicts_does_not_write(self, tmp_path, monkeypatch):
        """--write does NOT write when conflicts exist."""
        _git_init(str(tmp_path))
        target = tmp_path / "doc.md"
        target.write_text("## A\n\nOriginal.\n")
        base = _git_commit(str(tmp_path), "base")

        target.write_text("## A\n\nUser version.\n")
        new_file = tmp_path / "new.md"
        new_file.write_text("## A\n\nPlugin version.\n")

        monkeypatch.chdir(tmp_path)
        result = cmd_merge("doc.md", base, str(new_file), write=True)

        assert result["status"] == "conflicts"
        assert result["written"] is False
        # Original local content preserved
        assert "User version" in target.read_text()

    def test_no_local_changes_with_write(self, tmp_path, monkeypatch):
        """--write writes new content when local == base."""
        _git_init(str(tmp_path))
        target = tmp_path / "doc.md"
        target.write_text("## A\n\nContent.\n")
        base = _git_commit(str(tmp_path), "init")

        new_file = tmp_path / "new.md"
        new_file.write_text("## A\n\nUpdated.\n")

        monkeypatch.chdir(tmp_path)
        result = cmd_merge("doc.md", base, str(new_file), write=True)

        assert result["status"] == "no_local_changes"
        assert result["written"] is True
        assert "Updated" in target.read_text()

    def test_no_write_flag(self, tmp_path, monkeypatch):
        """Without --write, file is not modified."""
        _git_init(str(tmp_path))
        target = tmp_path / "doc.md"
        target.write_text("## A\n\nOriginal.\n")
        base = _git_commit(str(tmp_path), "base")

        new_file = tmp_path / "new.md"
        new_file.write_text("## A\n\nNew version.\n")

        monkeypatch.chdir(tmp_path)
        result = cmd_merge("doc.md", base, str(new_file), write=False)

        assert result["status"] == "no_local_changes"
        assert result["written"] is False
        # File NOT overwritten
        assert "Original" in target.read_text()

    def test_target_missing(self, tmp_path):
        new_file = tmp_path / "new.md"
        new_file.write_text("content")
        result = cmd_merge(str(tmp_path / "missing.md"), "abc", str(new_file))
        assert result["status"] == "error"

    def test_new_file_missing(self, tmp_path):
        target = tmp_path / "doc.md"
        target.write_text("content")
        result = cmd_merge(str(target), "abc", str(tmp_path / "missing.md"))
        assert result["status"] == "error"

    def test_bad_base_commit(self, tmp_path, monkeypatch):
        _git_init(str(tmp_path))
        target = tmp_path / "doc.md"
        target.write_text("content")
        _git_commit(str(tmp_path), "init")
        new_file = tmp_path / "new.md"
        new_file.write_text("new content")

        monkeypatch.chdir(tmp_path)
        result = cmd_merge("doc.md", "0000000", str(new_file))

        assert result["status"] == "error"
        assert "Cannot recover base" in result["message"]


# ============ Unit: cmd_pre_update (direct call) ============


class TestCmdPreUpdateUnit:
    def _setup(self, tmp_path):
        """Create project + plugin for pre-update tests."""
        mb = tmp_path / ".memory_bank"
        mb.mkdir()
        guides = mb / "guides"
        guides.mkdir()

        f1 = guides / "testing.md"
        f1.write_text("# Testing Guide\n\nContent.\n")
        h1 = compute_hash(f1)

        analysis = {
            "has_frontend": True, "has_backend": True,
            "has_tests": True, "has_database": False,
            "backend_language": "Python", "backend_framework": "Django"
        }
        (mb / "project-analysis.json").write_text(json.dumps(analysis, indent=2))

        plan = mb / "generation-plan.md"
        plan.write_text(dedent(f"""\
            ## Metadata

            Generation Base: (pending)

            ## Files

            | Status | File | Location | Lines | Hash | Source Hash |
            |--------|------|----------|-------|------|-------------|
            | [x] | testing.md | .memory_bank/guides/ | 3 | {h1} | aaa111 |
        """))

        plugin = tmp_path / "plugin"
        (plugin / "prompts" / "memory_bank" / "guides").mkdir(parents=True)
        (plugin / "static").mkdir(parents=True)

        prompt = plugin / "prompts" / "memory_bank" / "guides" / "testing.md.prompt"
        prompt.write_text("---\nfile: testing.md\ntarget_path: .memory_bank/guides/\npriority: 15\nconditional: null\n---\nInstructions.\n")

        manifest = plugin / "static" / "manifest.yaml"
        manifest.write_text("files:\n")

        # Create source-hashes.json
        sh = plugin / "source-hashes.json"
        sh.write_text(json.dumps({
            "prompts/memory_bank/guides/testing.md.prompt": "aaa111"
        }))

        return str(plugin)

    def test_basic(self, tmp_path, patch_globals):
        plugin = self._setup(tmp_path)
        patch_globals(tmp_path)
        result = cmd_pre_update(plugin)
        assert result["status"] == "success"
        assert "local_changes" in result
        assert "source_changes" in result
        assert "new_prompts" in result
        assert "removed_prompts" in result
        assert "static_files" in result
        assert "obsolete_files" in result
        assert "summary" in result
        assert result["tech_stack_diff"] is None
        assert result["tech_stack_diff_error"] is None

    def test_with_tech_diff(self, tmp_path, patch_globals):
        plugin = self._setup(tmp_path)
        new_analysis = {
            "has_frontend": True, "has_backend": True,
            "has_tests": True, "has_database": True,
            "backend_language": "Python", "backend_framework": "FastAPI"
        }
        new_path = tmp_path / "new-analysis.json"
        new_path.write_text(json.dumps(new_analysis))

        patch_globals(tmp_path)
        result = cmd_pre_update(plugin, str(new_path))
        assert result["status"] == "success"
        assert result["tech_stack_diff"] is not None
        # Django → FastAPI is HIGH impact
        assert len(result["tech_stack_diff"]["high"]) >= 1

    def test_no_analysis_file(self, tmp_path, patch_globals):
        mb = tmp_path / ".memory_bank"
        mb.mkdir()
        patch_globals(tmp_path)
        result = cmd_pre_update(str(tmp_path))
        assert result["status"] == "error"

    def test_detects_new_prompt(self, tmp_path, patch_globals):
        plugin = self._setup(tmp_path)
        # Add a new prompt that's not in the plan
        new_prompt = (Path(plugin) / "prompts" / "memory_bank" /
                      "guides" / "frontend.md.prompt")
        new_prompt.write_text(dedent("""\
            ---
            file: frontend.md
            target_path: .memory_bank/guides/
            priority: 16
            conditional: "has_frontend"
            ---
            Frontend instructions.
        """))

        patch_globals(tmp_path)
        result = cmd_pre_update(plugin)
        assert result["status"] == "success"
        assert len(result["new_prompts"]) == 1
        assert result["new_prompts"][0]["target"] == ".memory_bank/guides/frontend.md"

    def test_detects_removed_prompt_as_obsolete(self, tmp_path, patch_globals):
        """Prompt in plan but deleted from plugin → detected as obsolete."""
        plugin = self._setup(tmp_path)
        # Delete the prompt file that's referenced in the plan
        prompt = (Path(plugin) / "prompts" / "memory_bank" /
                  "guides" / "testing.md.prompt")
        prompt.unlink()

        patch_globals(tmp_path)
        result = cmd_pre_update(plugin)
        assert result["status"] == "success"
        # Deleted prompt is detected via obsolete_files (source doesn't exist)
        assert len(result["obsolete_files"]) == 1
        assert result["obsolete_files"][0]["target"] == ".memory_bank/guides/testing.md"

    def test_detects_removed_prompt_broken_frontmatter(self, tmp_path, patch_globals):
        """Prompt file exists but has broken frontmatter → detected as removed."""
        plugin = self._setup(tmp_path)
        # Break the prompt's frontmatter (remove 'file:' key)
        prompt = (Path(plugin) / "prompts" / "memory_bank" /
                  "guides" / "testing.md.prompt")
        prompt.write_text("---\ntarget_path: .memory_bank/guides/\npriority: 15\n---\nBroken.\n")

        patch_globals(tmp_path)
        result = cmd_pre_update(plugin)
        assert result["status"] == "success"
        # Prompt exists but can't be parsed → target not in prompt_targets
        # target_to_source_path returns .prompt path → detected as removed
        assert len(result["removed_prompts"]) == 1
        assert result["removed_prompts"][0]["target"] == ".memory_bank/guides/testing.md"

    def test_invalid_new_analysis_json(self, tmp_path, patch_globals):
        """Bad JSON in --new-analysis reports error, doesn't crash."""
        plugin = self._setup(tmp_path)
        bad_path = tmp_path / "bad.json"
        bad_path.write_text("not json!")

        patch_globals(tmp_path)
        result = cmd_pre_update(plugin, str(bad_path))
        assert result["status"] == "success"
        assert result["tech_stack_diff"] is None
        assert result["tech_stack_diff_error"] is not None
        assert "Failed to read" in result["tech_stack_diff_error"]

    def test_missing_new_analysis_file(self, tmp_path, patch_globals):
        """Non-existent --new-analysis reports error."""
        plugin = self._setup(tmp_path)

        patch_globals(tmp_path)
        result = cmd_pre_update(plugin, "/nonexistent/path.json")
        assert result["status"] == "success"
        assert result["tech_stack_diff"] is None
        assert "not found" in result["tech_stack_diff_error"].lower()


# ============ Unit: cmd_copy_static (direct call) ============


class TestCmdCopyStaticUnit:
    def _setup(self, tmp_path, analysis: dict = None):
        """Create plugin + project for copy-static tests."""
        mb = tmp_path / ".memory_bank"
        mb.mkdir(exist_ok=True)
        if analysis is None:
            analysis = {"has_frontend": True, "has_backend": True,
                        "backend_language": "Python"}
        (mb / "project-analysis.json").write_text(json.dumps(analysis))
        (mb / "generation-plan.md").write_text(
            "## Files\n\n| Status | File | Location | Lines | Hash | Source Hash |\n"
        )

        plugin = tmp_path / "plugin"
        static = plugin / "static"
        wf = static / "memory_bank" / "workflows"
        wf.mkdir(parents=True)
        (wf / "dev.md").write_text("# Dev Workflow\n\nContent.\n")
        (wf / "test.md").write_text("# Test Workflow\n\nContent.\n")

        agents = static / "agents"
        agents.mkdir(parents=True)
        (agents / "design.md").write_text("# Design Agent\n")

        manifest = static / "manifest.yaml"
        manifest.write_text(dedent("""\
            files:
              - source: memory_bank/workflows/dev.md
                target: .memory_bank/workflows/dev.md
                conditional: null

              - source: memory_bank/workflows/test.md
                target: .memory_bank/workflows/test.md
                conditional: null

              - source: agents/design.md
                target: .claude/agents/design.md
                conditional: "has_frontend"
        """))

        sh = plugin / "source-hashes.json"
        sh.write_text(json.dumps({
            "static/memory_bank/workflows/dev.md": "aaa",
            "static/memory_bank/workflows/test.md": "bbb",
            "static/agents/design.md": "ccc"
        }))

        return str(plugin)

    def test_copy_new_files(self, tmp_path, patch_globals):
        plugin = self._setup(tmp_path)
        patch_globals(tmp_path)
        result = cmd_copy_static(plugin)
        assert result["status"] == "success"
        assert result["summary"]["copied"] >= 2
        assert (tmp_path / ".memory_bank" / "workflows" / "dev.md").exists()
        assert (tmp_path / ".memory_bank" / "workflows" / "test.md").exists()
        assert (tmp_path / ".claude" / "agents" / "design.md").exists()

    def test_copy_with_clean_dir(self, tmp_path, patch_globals):
        plugin = self._setup(tmp_path)
        clean = tmp_path / "clean"
        patch_globals(tmp_path)
        result = cmd_copy_static(plugin, clean_dir=str(clean))
        assert result["status"] == "success"
        assert (clean / ".memory_bank" / "workflows" / "dev.md").exists()
        assert (clean / ".claude" / "agents" / "design.md").exists()

    def test_conditional_skip(self, tmp_path, patch_globals):
        plugin = self._setup(tmp_path, analysis={
            "has_frontend": False, "has_backend": True,
            "backend_language": "Python"
        })
        patch_globals(tmp_path)
        result = cmd_copy_static(plugin)
        assert result["status"] == "success"
        skipped_reasons = [s["reason"] for s in result["skipped"]]
        assert "condition_false" in skipped_reasons
        assert not (tmp_path / ".claude" / "agents" / "design.md").exists()

    def test_no_analysis(self, tmp_path, patch_globals):
        (tmp_path / ".memory_bank").mkdir()
        patch_globals(tmp_path)
        result = cmd_copy_static(str(tmp_path))
        assert result["status"] == "error"

    def test_no_manifest(self, tmp_path, patch_globals):
        mb = tmp_path / ".memory_bank"
        mb.mkdir()
        (mb / "project-analysis.json").write_text('{"has_frontend": true}')
        plugin = tmp_path / "empty_plugin"
        plugin.mkdir()
        patch_globals(tmp_path)
        result = cmd_copy_static(str(plugin))
        assert result["status"] == "error"
        assert "manifest" in result["message"].lower()

    def test_filter_categories(self, tmp_path, patch_globals):
        """Only process specified categories."""
        plugin = self._setup(tmp_path)
        patch_globals(tmp_path)
        # All files are "new" since they don't exist yet.
        # Filter to only "safe_overwrite" → nothing to copy.
        result = cmd_copy_static(plugin, filter_categories="safe_overwrite")
        assert result["status"] == "success"
        assert result["summary"]["copied"] == 0

    def test_filter_local_only(self, tmp_path, patch_globals):
        """Filtering by local_only skips files with that classification."""
        plugin = self._setup(tmp_path)
        # Create file that's locally modified but plugin unchanged → local_only
        wf_dir = tmp_path / ".memory_bank" / "workflows"
        wf_dir.mkdir(parents=True)
        target = wf_dir / "dev.md"
        target.write_text("locally modified content\n")

        mb = tmp_path / ".memory_bank"
        (mb / "generation-plan.md").write_text(dedent("""\
            ## Files

            | Status | File | Location | Lines | Hash | Source Hash |
            |--------|------|----------|-------|------|-------------|
            | [x] | dev.md | .memory_bank/workflows/ | 3 | different_hash | aaa |
        """))

        patch_globals(tmp_path)
        result = cmd_copy_static(plugin, filter_categories="local_only")
        assert result["status"] == "success"
        assert any(s["reason"] == "local_only" for s in result["skipped"])
        # File should NOT be overwritten
        assert "locally modified" in target.read_text()

    def test_filter_up_to_date(self, tmp_path, patch_globals):
        """Filtering by up_to_date skips files with that classification."""
        plugin = self._setup(tmp_path)
        # Create file that matches both hashes → up_to_date
        wf_dir = tmp_path / ".memory_bank" / "workflows"
        wf_dir.mkdir(parents=True)
        target = wf_dir / "dev.md"
        target.write_text("# Dev Workflow\n\nContent.\n")
        h = compute_hash(target)

        mb = tmp_path / ".memory_bank"
        (mb / "generation-plan.md").write_text(dedent(f"""\
            ## Files

            | Status | File | Location | Lines | Hash | Source Hash |
            |--------|------|----------|-------|------|-------------|
            | [x] | dev.md | .memory_bank/workflows/ | 3 | {h} | aaa |
        """))

        patch_globals(tmp_path)
        result = cmd_copy_static(plugin, filter_categories="up_to_date")
        assert result["status"] == "success"
        assert any(s["reason"] == "up_to_date" for s in result["skipped"])

    def test_source_not_found(self, tmp_path, patch_globals):
        """Missing source file → skipped."""
        mb = tmp_path / ".memory_bank"
        mb.mkdir()
        (mb / "project-analysis.json").write_text('{"has_frontend": true}')
        (mb / "generation-plan.md").write_text("## Files\n")

        plugin = tmp_path / "plugin"
        static = plugin / "static"
        static.mkdir(parents=True)
        manifest = static / "manifest.yaml"
        manifest.write_text(dedent("""\
            files:
              - source: missing/file.md
                target: .memory_bank/file.md
                conditional: null
        """))
        (plugin / "source-hashes.json").write_text("{}")

        patch_globals(tmp_path)
        result = cmd_copy_static(str(plugin))
        assert result["status"] == "success"
        assert any(s["reason"] == "source_not_found" for s in result["skipped"])

    def test_safe_overwrite(self, tmp_path, patch_globals):
        """Existing file, no local changes, plugin updated → overwritten."""
        plugin = self._setup(tmp_path)
        # Pre-create target file and add to plan with old source hash
        wf_dir = tmp_path / ".memory_bank" / "workflows"
        wf_dir.mkdir(parents=True)
        target = wf_dir / "dev.md"
        target.write_text("# Dev Workflow\n\nContent.\n")
        h = compute_hash(target)

        mb = tmp_path / ".memory_bank"
        (mb / "generation-plan.md").write_text(dedent(f"""\
            ## Files

            | Status | File | Location | Lines | Hash | Source Hash |
            |--------|------|----------|-------|------|-------------|
            | [x] | dev.md | .memory_bank/workflows/ | 3 | {h} | old_hash |
        """))

        patch_globals(tmp_path)
        result = cmd_copy_static(plugin, filter_categories="safe_overwrite")
        assert result["status"] == "success"
        assert result["summary"]["copied"] >= 1
        assert any(c["action"] == "safe_overwrite" for c in result["copied"])

    def test_merge_needed_no_base_commit(self, tmp_path, patch_globals):
        """merge_needed without --base-commit → overwrites."""
        plugin = self._setup(tmp_path)
        # Create an existing modified file
        wf_dir = tmp_path / ".memory_bank" / "workflows"
        wf_dir.mkdir(parents=True)
        target = wf_dir / "dev.md"
        target.write_text("# Dev Workflow\n\nLocally modified.\n")

        mb = tmp_path / ".memory_bank"
        (mb / "generation-plan.md").write_text(dedent("""\
            ## Files

            | Status | File | Location | Lines | Hash | Source Hash |
            |--------|------|----------|-------|------|-------------|
            | [x] | dev.md | .memory_bank/workflows/ | 3 | different | old_src |
        """))

        patch_globals(tmp_path)
        result = cmd_copy_static(plugin, filter_categories="merge_needed")
        assert result["status"] == "success"
        assert any(c.get("action") == "overwrite_no_base" for c in result["copied"])

    def test_merge_needed_with_base_auto_merge(self, tmp_path, patch_globals):
        """merge_needed with --base-commit, no conflicts → auto-merged."""
        _git_init(str(tmp_path))

        plugin = self._setup(tmp_path)
        wf_dir = tmp_path / ".memory_bank" / "workflows"
        wf_dir.mkdir(parents=True)
        target = wf_dir / "dev.md"
        target.write_text("## A\n\nOriginal A.\n\n## B\n\nOriginal B.\n")
        base = _git_commit(str(tmp_path), "base")

        h = compute_hash(target)
        # Modify locally (section A)
        target.write_text("## A\n\nUser modified A.\n\n## B\n\nOriginal B.\n")

        # Plugin has different content (section B)
        plugin_file = Path(plugin) / "static" / "memory_bank" / "workflows" / "dev.md"
        plugin_file.write_text("## A\n\nOriginal A.\n\n## B\n\nPlugin updated B.\n")

        mb = tmp_path / ".memory_bank"
        (mb / "generation-plan.md").write_text(dedent(f"""\
            ## Files

            | Status | File | Location | Lines | Hash | Source Hash |
            |--------|------|----------|-------|------|-------------|
            | [x] | dev.md | .memory_bank/workflows/ | 3 | {h} | old_src |
        """))

        patch_globals(tmp_path)
        result = cmd_copy_static(
            plugin, filter_categories="merge_needed",
            base_commit=base
        )
        assert result["status"] == "success"
        assert result["summary"]["auto_merged"] >= 1
        content = target.read_text()
        assert "User modified A" in content
        assert "Plugin updated B" in content
        assert "Original A" not in content
        assert "Original B" not in content

    def test_merge_needed_conflict_does_not_write(self, tmp_path, patch_globals):
        """merge_needed with conflicts → does NOT overwrite target."""
        _git_init(str(tmp_path))

        plugin = self._setup(tmp_path)
        wf_dir = tmp_path / ".memory_bank" / "workflows"
        wf_dir.mkdir(parents=True)
        target = wf_dir / "dev.md"
        target.write_text("## A\n\nOriginal.\n")
        base = _git_commit(str(tmp_path), "base")

        h = compute_hash(target)
        # Both sides modify same section
        target.write_text("## A\n\nUser changed.\n")

        plugin_file = Path(plugin) / "static" / "memory_bank" / "workflows" / "dev.md"
        plugin_file.write_text("## A\n\nPlugin changed.\n")

        mb = tmp_path / ".memory_bank"
        (mb / "generation-plan.md").write_text(dedent(f"""\
            ## Files

            | Status | File | Location | Lines | Hash | Source Hash |
            |--------|------|----------|-------|------|-------------|
            | [x] | dev.md | .memory_bank/workflows/ | 3 | {h} | old_src |
        """))

        patch_globals(tmp_path)
        result = cmd_copy_static(
            plugin, filter_categories="merge_needed",
            base_commit=base
        )
        assert result["status"] == "success"
        assert result["summary"]["conflicts"] >= 1
        # Target should still have the local content (not overwritten)
        assert "User changed" in target.read_text()

    def test_merge_needed_bad_base_content(self, tmp_path, patch_globals):
        """git show fails for base → reported as conflict."""
        _git_init(str(tmp_path))
        plugin = self._setup(tmp_path)

        wf_dir = tmp_path / ".memory_bank" / "workflows"
        wf_dir.mkdir(parents=True)
        target = wf_dir / "dev.md"
        target.write_text("# Dev\n")
        _git_commit(str(tmp_path), "init")

        h = compute_hash(target)
        target.write_text("# Dev Modified\n")

        mb = tmp_path / ".memory_bank"
        (mb / "generation-plan.md").write_text(dedent(f"""\
            ## Files

            | Status | File | Location | Lines | Hash | Source Hash |
            |--------|------|----------|-------|------|-------------|
            | [x] | dev.md | .memory_bank/workflows/ | 1 | {h} | old |
        """))

        patch_globals(tmp_path)
        result = cmd_copy_static(
            plugin, filter_categories="merge_needed",
            base_commit="0000000000"  # non-existent commit
        )
        assert result["status"] == "success"
        assert any(
            c.get("reason") == "no_base_content"
            for c in result["has_conflicts"]
        )


# ============ Unit: parse_prompt_frontmatter edge cases ============


class TestParsePromptFrontmatterEdgeCases:
    def test_boolean_values(self, tmp_path):
        f = tmp_path / "test.prompt"
        f.write_text("---\nfile: test.md\ntarget_path: ./\npriority: 1\nconditional: true\n---\nContent.\n")
        result = parse_prompt_frontmatter(f)
        assert result["conditional"] is True

    def test_false_value(self, tmp_path):
        f = tmp_path / "test.prompt"
        f.write_text("---\nfile: test.md\ntarget_path: ./\npriority: 1\nconditional: false\n---\nContent.\n")
        result = parse_prompt_frontmatter(f)
        assert result["conditional"] is False

    def test_unquoted_string_value(self, tmp_path):
        f = tmp_path / "test.prompt"
        f.write_text("---\nfile: test.md\ntarget_path: ./\npriority: 1\nconditional: has_frontend\n---\nContent.\n")
        result = parse_prompt_frontmatter(f)
        assert result["conditional"] == "has_frontend"

    def test_single_quoted_value(self, tmp_path):
        f = tmp_path / "test.prompt"
        f.write_text("---\nfile: test.md\ntarget_path: ./\nconditional: 'has_tests'\n---\n")
        result = parse_prompt_frontmatter(f)
        assert result["conditional"] == "has_tests"

    def test_frontmatter_with_comment(self, tmp_path):
        f = tmp_path / "test.prompt"
        f.write_text("---\nfile: test.md\ntarget_path: ./\n# A comment\npriority: 5\n---\nContent.\n")
        result = parse_prompt_frontmatter(f)
        assert result["priority"] == 5


# ============ Unit: compare_tech_stacks edge cases ============


class TestCompareTechStacksEdgeCases:
    def test_framework_removed(self):
        old = {"frontend_framework": "React"}
        new = {"frontend_framework": None}
        result = compare_tech_stacks(old, new)
        assert any(c["reason"] == "framework_removed" for c in result["medium"])

    def test_capability_removed(self):
        old = {"has_database": True}
        new = {"has_database": False}
        result = compare_tech_stacks(old, new)
        assert any(c["reason"] == "capability_removed" for c in result["medium"])

    def test_other_field_change(self):
        old = {"database": "PostgreSQL"}
        new = {"database": "MySQL"}
        result = compare_tech_stacks(old, new)
        assert any(c["reason"] == "value_changed" for c in result["low"])

    def test_other_field_added(self):
        old = {}
        new = {"test_command": "pytest"}
        result = compare_tech_stacks(old, new)
        assert any(c["reason"] == "value_changed" for c in result["low"])

    def test_version_both_none_no_change(self):
        old = {"backend_framework_version": None}
        new = {"backend_framework_version": None}
        result = compare_tech_stacks(old, new)
        assert result == {"high": [], "medium": [], "low": []}


# ============ cmd_check_existing ============


class TestCheckExisting:
    def test_no_memory_bank(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = cmd_check_existing(str(tmp_path / ".memory_bank"))
        assert result["exists"] is False
        assert result["modified_count"] == 0
        assert result["base_commit"] is None

    def test_existing_environment(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        mb = tmp_path / ".memory_bank"
        mb.mkdir()
        plan = mb / "generation-plan.md"
        plan.write_text(
            "# Generation Plan\n\n"
            "## Metadata\n\nGeneration Base: abc123\n\n"
            "## Files\n\n"
            "| Status | File | Location | Lines | Hash | Source Hash |\n"
            "|--------|------|----------|-------|------|-------------|\n"
            "| [x] | README.md | .memory_bank/ | 10 | deadbeef | aabb1122 |\n"
        )
        # Patch the GENERATION_PLAN via monkeypatch (auto-restored on teardown)
        monkeypatch.setitem(GENERATION_PLAN_REF, "GENERATION_PLAN", plan)
        result = cmd_check_existing(str(mb))
        assert result["exists"] is True
        assert result["base_commit"] == "abc123"
        assert result["total_files"] == 1


# ============ cmd_plan_generation ============


class TestPlanGeneration:
    def test_basic_plan(self, tmp_path, monkeypatch):
        """plan-generation scans prompts + manifest and outputs filtered items."""
        monkeypatch.chdir(tmp_path)

        # Create a minimal plugin structure
        plugin = tmp_path / "plugin"
        prompts_dir = plugin / "prompts" / "memory_bank" / "guides"
        prompts_dir.mkdir(parents=True)
        (prompts_dir / "test-guide.md.prompt").write_text(
            "---\n"
            "file: test-guide.md\n"
            "target_path: .memory_bank/guides/\n"
            "priority: 10\n"
            "conditional: null\n"
            "---\n"
            "Generate a test guide.\n"
        )
        # Add a conditional prompt that should be skipped
        (prompts_dir / "frontend-guide.md.prompt").write_text(
            "---\n"
            "file: frontend-guide.md\n"
            "target_path: .memory_bank/guides/\n"
            "priority: 20\n"
            "conditional: has_frontend\n"
            "---\n"
            "Generate frontend guide.\n"
        )

        # Create minimal manifest
        static_dir = plugin / "static"
        static_dir.mkdir()
        (static_dir / "manifest.yaml").write_text(
            "files:\n"
            "  - source: memory_bank/workflows/test.md\n"
            "    target: .memory_bank/workflows/test.md\n"
            "    conditional: null\n"
        )
        (static_dir / "memory_bank" / "workflows").mkdir(parents=True)
        (static_dir / "memory_bank" / "workflows" / "test.md").write_text("# Test")

        # Create analysis file (no frontend)
        analysis_file = tmp_path / "analysis.json"
        analysis_file.write_text(json.dumps({
            "has_frontend": False,
            "has_backend": True,
            "backend_language": "Python",
        }))

        # Create output dir
        output = tmp_path / "output" / "generation-plan.md"

        result = cmd_plan_generation(
            str(plugin), str(analysis_file), str(output),
        )

        assert result["status"] == "success"
        assert result["prompts"] == 1  # only null conditional passes
        assert result["statics"] == 1
        assert result["total"] == 2
        assert output.exists()

        # Check the plan items
        items = result["plan"]
        prompt_items = [i for i in items if i["type"] == "prompt"]
        assert len(prompt_items) == 1
        assert "test-guide" in prompt_items[0]["target"]

    def test_missing_analysis_file(self, tmp_path):
        result = cmd_plan_generation(str(tmp_path), str(tmp_path / "missing.json"))
        assert result["status"] == "error"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
