#!/usr/bin/env python3
"""Tests for the analyze-local-changes skill script."""

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import dedent

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


class TestComputeCLI:
    def test_compute_single_file(self):
        with TemporaryDirectory() as tmp:
            f = Path(tmp) / "test.md"
            f.write_text("Hello world\n")
            out = run(["compute", str(f)], tmp)
            assert out["status"] == "success"
            assert len(out["files"]) == 1
            assert out["files"][0]["hash"]
            assert out["files"][0]["lines"] == 1

    def test_compute_missing_file(self):
        with TemporaryDirectory() as tmp:
            out = run(["compute", "/nonexistent/file.md"], tmp)
            assert out["files"][0]["error"] == "File not found"

    def test_compute_deterministic(self):
        with TemporaryDirectory() as tmp:
            f = Path(tmp) / "test.md"
            f.write_text("Same content\n")
            out1 = run(["compute", str(f)], tmp)
            out2 = run(["compute", str(f)], tmp)
            assert out1["files"][0]["hash"] == out2["files"][0]["hash"]

    def test_compute_different_content(self):
        with TemporaryDirectory() as tmp:
            f = Path(tmp) / "test.md"
            f.write_text("Version 1\n")
            h1 = run(["compute", str(f)], tmp)["files"][0]["hash"]
            f.write_text("Version 2\n")
            h2 = run(["compute", str(f)], tmp)["files"][0]["hash"]
            assert h1 != h2


# ============ CLI: detect ============


class TestDetectCLI:
    def _setup_project(self, tmp: str):
        """Create a minimal project with generation-plan.md."""
        mb = Path(tmp) / ".memory_bank"
        mb.mkdir()
        guides = mb / "guides"
        guides.mkdir()

        f1 = guides / "testing.md"
        f1.write_text("# Testing Guide\n\nContent.\n")

        f2 = guides / "backend.md"
        f2.write_text("# Backend Guide\n\nContent.\n")

        # Compute actual hashes
        h1 = run(["compute", str(f1)], tmp)["files"][0]["hash"]
        h2 = run(["compute", str(f2)], tmp)["files"][0]["hash"]

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

    def test_detect_no_changes(self):
        with TemporaryDirectory() as tmp:
            self._setup_project(tmp)
            out = run(["detect"], tmp)
            assert out["status"] == "success"
            assert out["summary"]["modified"] == 0
            assert out["summary"]["unchanged"] == 2

    def test_detect_modified_file(self):
        with TemporaryDirectory() as tmp:
            f1, _ = self._setup_project(tmp)
            f1.write_text("# Testing Guide\n\nModified content.\n")
            out = run(["detect"], tmp)
            assert out["summary"]["modified"] == 1
            assert ".memory_bank/guides/testing.md" in out["modified"]

    def test_detect_non_md_files(self):
        """Non-markdown files (e.g. .py) in .claude/ are detected, not reported as missing."""
        with TemporaryDirectory() as tmp:
            mb = Path(tmp) / ".memory_bank"
            mb.mkdir()
            claude = Path(tmp) / ".claude"
            skills = claude / "skills"
            skills.mkdir(parents=True)

            py_file = skills / "defer.py"
            py_file.write_text("#!/usr/bin/env python3\nprint('hello')\n")

            h = run(["compute", str(py_file)], tmp)["files"][0]["hash"]

            plan = mb / "generation-plan.md"
            plan.write_text(dedent(f"""\
                ## Files

                | Status | File | Location | Lines | Hash | Source Hash |
                |--------|------|----------|-------|------|-------------|
                | [x] | defer.py | .claude/skills/ | 2 | {h} | aaa111 |
            """))

            out = run(["detect"], tmp)
            assert out["status"] == "success"
            assert out["summary"]["missing"] == 0
            assert ".claude/skills/defer.py" in out["unchanged"]

    def test_detect_missing_plan(self):
        with TemporaryDirectory() as tmp:
            out = run(["detect"], tmp)
            assert out["status"] == "error"


# ============ CLI: merge ============


class TestMergeCLI:
    def test_merge_requires_git(self):
        """Merge needs git to recover base — fails gracefully without it."""
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "file.md"
            target.write_text("local content")
            new = Path(tmp) / "new.md"
            new.write_text("new content")
            out = run(
                ["merge", str(target), "--base-commit", "nonexistent", "--new-file", str(new)],
                tmp,
            )
            assert out["status"] == "error"

    def test_merge_in_git_repo(self):
        """Full merge test inside a real git repo."""
        with TemporaryDirectory() as tmp:
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
            f = Path(tmp) / "doc.md"
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
            new_file = Path(tmp) / "new_version.md"
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

    def test_merge_no_local_changes(self):
        """If local == base, just returns new version."""
        with TemporaryDirectory() as tmp:
            subprocess.run(["git", "init"], cwd=tmp, capture_output=True)
            subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp, capture_output=True)
            subprocess.run(["git", "config", "user.name", "T"], cwd=tmp, capture_output=True)

            f = Path(tmp) / "doc.md"
            f.write_text("## A\n\nContent.\n")
            subprocess.run(["git", "add", "."], cwd=tmp, capture_output=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=tmp, capture_output=True)
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=tmp, capture_output=True, text=True
            ).stdout.strip()

            new_file = Path(tmp) / "new.md"
            new_file.write_text("## A\n\nUpdated.\n")

            out = run(["merge", "doc.md", "--base-commit", base, "--new-file", str(new_file)], tmp)
            assert out["status"] == "no_local_changes"
            assert "Updated" in out["merged_content"]


# ============ CLI: commit-generation ============


class TestCommitGenerationCLI:
    def _init_repo(self, tmp: str):
        subprocess.run(["git", "init"], cwd=tmp, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmp, capture_output=True)

    def test_simple_commit(self):
        """Without --clean-dir: single commit, base == commit."""
        with TemporaryDirectory() as tmp:
            self._init_repo(tmp)

            # Create files
            mb = Path(tmp) / ".memory_bank"
            mb.mkdir()
            (mb / "README.md").write_text("# README\n")
            plan = mb / "generation-plan.md"
            plan.write_text("## Metadata\n\nGeneration Base: (pending)\nGeneration Commit: (pending)\n")

            # Need CLAUDE.md to exist for git add
            (Path(tmp) / "CLAUDE.md").write_text("# CLAUDE\n")
            (Path(tmp) / ".claude").mkdir()

            out = run(["commit-generation", "--plugin-version", "1.3.0"], tmp)
            assert out["status"] == "success"
            assert out["generation_base"] == out["generation_commit"]
            assert out["merge_applied"] is False

            # Check metadata was updated in plan
            plan_content = plan.read_text()
            assert out["generation_base"] in plan_content

    def test_commit_with_clean_dir(self):
        """With --clean-dir: two commits if clean differs from current."""
        with TemporaryDirectory() as tmp:
            self._init_repo(tmp)

            mb = Path(tmp) / ".memory_bank"
            mb.mkdir()
            guides = mb / "guides"
            guides.mkdir()

            # Current file has merged content
            (guides / "testing.md").write_text("# Testing\n\nPlugin content.\n\n## User Section\n\nCustom.\n")
            plan = mb / "generation-plan.md"
            plan.write_text("## Metadata\n\nGeneration Base: (pending)\nGeneration Commit: (pending)\n")
            (Path(tmp) / "CLAUDE.md").write_text("# CLAUDE\n")
            (Path(tmp) / ".claude").mkdir()

            # Clean dir has plugin-only version
            clean = Path(tmp) / "clean"
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

    def test_commit_no_changes(self):
        """Error when nothing to commit."""
        with TemporaryDirectory() as tmp:
            self._init_repo(tmp)
            # Create and commit files first
            mb = Path(tmp) / ".memory_bank"
            mb.mkdir()
            (mb / "README.md").write_text("# README\n")
            (Path(tmp) / "CLAUDE.md").write_text("# CLAUDE\n")
            (Path(tmp) / ".claude").mkdir()
            subprocess.run(["git", "add", "."], cwd=tmp, capture_output=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=tmp, capture_output=True)

            # Now try commit-generation with no new changes
            out = run(["commit-generation", "--plugin-version", "1.0.0"], tmp)
            assert out["status"] == "error"


# ============ Metadata helpers ============


class TestMetadataHelpers:
    def test_parse_metadata(self):
        with TemporaryDirectory() as tmp:
            plan = Path(tmp) / ".memory_bank" / "generation-plan.md"
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
            import types
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

    def test_update_metadata_existing_key(self):
        with TemporaryDirectory() as tmp:
            plan = Path(tmp) / "plan.md"
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

    def test_update_metadata_new_key(self):
        with TemporaryDirectory() as tmp:
            plan = Path(tmp) / "plan.md"
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
    def test_parse_plan_table(self):
        with TemporaryDirectory() as tmp:
            plan = Path(tmp) / ".memory_bank" / "generation-plan.md"
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


class TestRecomputeSourceHashes:
    def test_creates_json(self):
        """Creates source-hashes.json with correct hashes."""
        with TemporaryDirectory() as tmp:
            # Create prompts/
            prompts = Path(tmp) / "prompts"
            prompts.mkdir()
            p1 = prompts / "CLAUDE.md.prompt"
            p1.write_text("prompt content\n")
            mb_prompts = prompts / "memory_bank"
            mb_prompts.mkdir()
            p2 = mb_prompts / "README.md.prompt"
            p2.write_text("readme prompt\n")

            # Create static/
            static = Path(tmp) / "static"
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
            json_path = Path(tmp) / "source-hashes.json"
            assert json_path.exists()
            data = json.loads(json_path.read_text())
            assert "prompts/CLAUDE.md.prompt" in data
            assert "prompts/memory_bank/README.md.prompt" in data
            assert "static/memory_bank/workflows/dev.md" in data

            # Verify hashes are correct (8-char MD5)
            assert len(data["prompts/CLAUDE.md.prompt"]) == 8
            expected_hash = compute_hash(p1)
            assert data["prompts/CLAUDE.md.prompt"] == expected_hash

    def test_excludes_manifest(self):
        """manifest.yaml is not included in source-hashes.json."""
        with TemporaryDirectory() as tmp:
            static = Path(tmp) / "static"
            static.mkdir()
            (static / "manifest.yaml").write_text("manifest\n")
            (static / "file.md").write_text("content\n")

            out = run(["recompute-source-hashes", "--plugin-root", tmp], tmp)
            assert out["files"] == 1

            data = json.loads((Path(tmp) / "source-hashes.json").read_text())
            assert "static/manifest.yaml" not in data
            assert "static/file.md" in data

    def test_excludes_pycache(self):
        """__pycache__ files are not included."""
        with TemporaryDirectory() as tmp:
            static = Path(tmp) / "static"
            cache = static / "scripts" / "__pycache__"
            cache.mkdir(parents=True)
            (cache / "foo.cpython-314.pyc").write_bytes(b"\x00\x01")
            (static / "scripts" / "real.py").write_text("code\n")

            out = run(["recompute-source-hashes", "--plugin-root", tmp], tmp)
            data = json.loads((Path(tmp) / "source-hashes.json").read_text())
            assert not any("__pycache__" in k for k in data)
            assert "static/scripts/real.py" in data


# ============ CLI: update-plan ============


class TestUpdatePlan:
    def _setup_project(self, tmp: str):
        """Create project with generation-plan.md and some generated files."""
        mb = Path(tmp) / ".memory_bank"
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
        plugin = Path(tmp) / "plugin"
        plugin.mkdir()
        prompts = plugin / "prompts" / "memory_bank" / "guides"
        prompts.mkdir(parents=True)
        (prompts / "testing.md.prompt").write_text("testing prompt\n")
        (prompts / "backend.md.prompt").write_text("backend prompt\n")

        # Generate source-hashes.json
        run(["recompute-source-hashes", "--plugin-root", str(plugin)], tmp)

        return f1, f2, plan, str(plugin)

    def test_marks_complete(self):
        """[x], hash, source_hash, lines are updated."""
        with TemporaryDirectory() as tmp:
            f1, _, plan, plugin = self._setup_project(tmp)
            out = run(
                ["update-plan", ".memory_bank/guides/testing.md", "--plugin-root", plugin],
                tmp,
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

    def test_multiple_files(self):
        """Multiple files updated in one call."""
        with TemporaryDirectory() as tmp:
            f1, f2, plan, plugin = self._setup_project(tmp)
            out = run(
                [
                    "update-plan",
                    ".memory_bank/guides/testing.md",
                    ".memory_bank/guides/backend.md",
                    "--plugin-root",
                    plugin,
                ],
                tmp,
            )
            assert out["status"] == "success"
            assert len(out["updated"]) == 2

            content = plan.read_text()
            assert content.count("[x]") == 2

    def test_auto_add_missing_row(self):
        """File not in plan table is auto-added to correct section."""
        with TemporaryDirectory() as tmp:
            mb = Path(tmp) / ".memory_bank"
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

            plugin = Path(tmp) / "plugin"
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
                tmp,
            )
            assert out["status"] == "success"
            assert len(out["updated"]) == 1  # testing.md was updated
            assert len(out["added"]) == 1    # new-guide.md was added
            assert out["added"][0]["file"] == ".memory_bank/guides/new-guide.md"

            content = plan.read_text()
            assert "new-guide.md" in content
            assert content.count("[x]") == 2

    def test_remove_row(self):
        """--remove deletes rows from generation plan."""
        with TemporaryDirectory() as tmp:
            mb = Path(tmp) / ".memory_bank"
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

            plugin = Path(tmp) / "plugin"
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
                tmp,
            )
            assert out["status"] == "success"
            assert len(out["removed"]) == 1
            assert out["removed"][0]["file"] == ".memory_bank/guides/obsolete.md"

            content = plan.read_text()
            assert "obsolete.md" not in content
            assert "testing.md" in content

    def test_remove_nonexistent_row(self):
        """--remove for file not in plan produces warning."""
        with TemporaryDirectory() as tmp:
            mb = Path(tmp) / ".memory_bank"
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

            plugin = Path(tmp) / "plugin"
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
                tmp,
            )
            assert out["status"] == "success"
            assert any(
                w["warning"] == "Row not found for removal"
                for w in out.get("warnings", [])
            )

    def test_missing_source_hash(self):
        """File with no source hash → warning, empty field."""
        with TemporaryDirectory() as tmp:
            mb = Path(tmp) / ".memory_bank"
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
            plugin = Path(tmp) / "plugin"
            plugin.mkdir()
            (plugin / "source-hashes.json").write_text("{}\n")

            out = run(
                ["update-plan", ".memory_bank/orphan.md", "--plugin-root", str(plugin)],
                tmp,
            )
            assert out["status"] == "success"
            assert len(out["updated"]) == 1
            assert out["updated"][0]["source_hash"] is None


# ============ compute-source reads from JSON ============


class TestComputeSourceJSON:
    def test_reads_from_json(self):
        """When source-hashes.json exists, uses hash from it."""
        with TemporaryDirectory() as tmp:
            plugin = Path(tmp) / "plugin"
            prompts = plugin / "prompts"
            prompts.mkdir(parents=True)
            prompt_file = prompts / "CLAUDE.md.prompt"
            prompt_file.write_text("content\n")

            # Create source-hashes.json with a known hash
            hashes = {"prompts/CLAUDE.md.prompt": "fakehash"}
            (plugin / "source-hashes.json").write_text(json.dumps(hashes))

            out = run(
                ["compute-source", "prompts/CLAUDE.md.prompt", "--plugin-root", str(plugin)],
                tmp,
            )
            assert out["status"] == "success"
            # Should use the JSON hash, not compute from file
            assert out["files"][0]["hash"] == "fakehash"

    def test_fallback_without_json(self):
        """Without source-hashes.json, computes from file."""
        with TemporaryDirectory() as tmp:
            plugin = Path(tmp) / "plugin"
            prompts = plugin / "prompts"
            prompts.mkdir(parents=True)
            prompt_file = prompts / "CLAUDE.md.prompt"
            prompt_file.write_text("content\n")

            out = run(
                ["compute-source", "prompts/CLAUDE.md.prompt", "--plugin-root", str(plugin)],
                tmp,
            )
            assert out["status"] == "success"
            # Should compute real hash from file
            expected = compute_hash(prompt_file)
            assert out["files"][0]["hash"] == expected


# ============ detect-source-changes uses JSON ============


class TestDetectSourceChangesJSON:
    def test_uses_json(self):
        """detect-source-changes reads from source-hashes.json when available."""
        with TemporaryDirectory() as tmp:
            # Setup: generation-plan.md with a stored source hash
            mb = Path(tmp) / ".memory_bank"
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
            plugin = Path(tmp) / "plugin"
            prompts = plugin / "prompts" / "memory_bank" / "guides"
            prompts.mkdir(parents=True)
            (prompts / "testing.md.prompt").write_text("prompt\n")

            hashes = {"prompts/memory_bank/guides/testing.md.prompt": "changed!"}
            (plugin / "source-hashes.json").write_text(json.dumps(hashes))

            out = run(
                ["detect-source-changes", "--plugin-root", str(plugin)],
                tmp,
            )
            assert out["status"] == "success"
            assert len(out["changed"]) == 1
            assert out["changed"][0]["current_hash"] == "changed!"
            assert out["changed"][0]["stored_hash"] == "original"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
