import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

COMPETENCIES_DIR = REPO_ROOT / "static" / "workflows" / "code-review" / "competencies"
STATIC_COMMANDS_DIR = REPO_ROOT / "static" / "commands"
STATIC_SKILLS_DIR = REPO_ROOT / "static" / "skills"

README_PROMPT_PATH = REPO_ROOT / "prompts" / "memory_bank" / "README.md.prompt"


def _read_utf8(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def _strip_fenced_code_blocks(markdown: str) -> str:
    """
    Remove fenced code blocks (``` / ```` / etc.) so link checks only apply to
    prose, not embedded templates/examples.
    """
    out_lines: list[str] = []
    in_fence = False
    fence_len = 0

    for line in markdown.splitlines(keepends=True):
        stripped = line.lstrip()

        if not in_fence:
            if stripped.startswith("```"):
                fence_len = len(stripped) - len(stripped.lstrip("`"))
                if fence_len >= 3:
                    in_fence = True
                    continue
            out_lines.append(line)
            continue

        # In a fenced code block: skip until we hit a closing fence of >= the opening length.
        if stripped.startswith("`" * fence_len):
            in_fence = False
            fence_len = 0
        continue

    return "".join(out_lines)


def _strip_inline_code(markdown: str) -> str:
    # Good enough for our templates (single-line inline code).
    return re.sub(r"`[^`]*`", "", markdown)



def test_readme_prompt_lists_only_shipped_commands() -> None:
    """
    The generated `.memory_bank/README.md` is the primary navigation hub.
    Its command list must not drift from what we actually deploy.
    """
    shipped_commands = {p.stem for p in STATIC_COMMANDS_DIR.glob("*.md")}
    # Skills deployed to target projects are also invocable as /skill-name
    shipped_skills = {p.parent.name for p in STATIC_SKILLS_DIR.glob("*/SKILL.md")}
    shipped_commands |= shipped_skills
    assert shipped_commands, f"No static commands or skills found in: {STATIC_COMMANDS_DIR}"

    content = _read_utf8(README_PROMPT_PATH)

    # Extract slash command names from backticked command strings like:
    # ` /create-protocol [args] `
    cmd_name_re = re.compile(r"`/([a-z0-9-]+(?::[a-z0-9-]+)?)")
    mentioned = set(cmd_name_re.findall(content))

    # Allow namespaced plugin commands for gardening automation.
    plugin_namespace = "memento"
    plugin_commands = {p.stem for p in (REPO_ROOT / "commands").glob("*.md")}
    plugin_skills = {p.parent.name for p in (REPO_ROOT / "skills").glob("*/SKILL.md")}
    plugin_slash_names = plugin_commands | plugin_skills

    unknown: list[str] = []
    for cmd in sorted(mentioned):
        if ":" in cmd:
            ns, name = cmd.split(":", 1)
            if ns != plugin_namespace or name not in plugin_slash_names:
                unknown.append(cmd)
            continue

        if cmd not in shipped_commands:
            unknown.append(cmd)

    assert not unknown, (
        "README prompt mentions commands we don't ship (or plugin commands that don't exist):\n"
        + "\n".join(f"- /{c}" for c in unknown)
        + "\n\nShipped project commands:\n"
        + "\n".join(f"- /{c}" for c in sorted(shipped_commands))
        + "\n\nAvailable plugin commands/skills (namespaced):\n"
        + "\n".join(f"- /{plugin_namespace}:{c}" for c in sorted(plugin_slash_names))
    )


def test_readme_prompt_is_a_map_not_a_manual() -> None:
    """
    Harness principle: the primary entry doc must stay small and navigational.

    The README is loaded on every /prime — every line must earn its place in
    the context window.  Target: 25-35 lines (a map, not a manual).
    """
    content = _read_utf8(README_PROMPT_PATH)

    m = re.search(r"\*\*Length\*\*:\s*(\d+)\s*-\s*(\d+)\s*lines", content)
    assert m, "README prompt must declare a Length range like '**Length**: 25-35 lines'"

    upper = int(m.group(2))
    assert upper <= 50, f"README prompt length upper bound too large: {upper} (expected <= 50)"


def test_readme_prompt_has_no_encyclopedia_sections() -> None:
    """
    Sections removed from the README prompt to keep generated output lean.

    These sections were stripped because the AI agent already knows them,
    they duplicate skill/command discovery, or they target human readers
    rather than the AI audience.
    """
    content = _read_utf8(README_PROMPT_PATH)

    removed_sections = [
        "What is the Memory Bank",
        "For Developers",
        "Directory Structure",
        "Navigation Tips",
        "Maintenance",
        "Available Commands",
        "Available Agents",
    ]

    found = [s for s in removed_sections if s in content]
    assert not found, (
        "README prompt still contains sections that should be removed:\n"
        + "\n".join(f"- {s}" for s in found)
    )


def test_readme_prompt_no_deleted_guide_references() -> None:
    """
    Guardrail: README prompt must not reference guides/workflows that were
    deleted in the cleanup protocol.
    """
    content = _read_utf8(README_PROMPT_PATH)

    deleted_refs = [
        "ai-agent-handbook",
        "code-review-guidelines",
        "testing.md",
        "testing-backend",
        "testing-frontend",
        "bug-fixing",
        "agent-orchestration",
        "create-prd.md",
        "create-spec.md",
        "create-protocol.md",
        "update-memory-bank.md",
        "doc-gardening.md",
        "workflows/",
    ]

    found = [r for r in deleted_refs if r in content]
    assert not found, (
        "README prompt references deleted files/sections:\n"
        + "\n".join(f"- {r}" for r in found)
    )


def test_agents_wrappers_point_to_claude_md() -> None:
    """
    Guardrail: keep a single entry point for repo rules.

    `AGENTS.md` files are thin wrappers so agents reliably load `CLAUDE.md`.
    """
    expected_line = "READ ./CLAUDE.md"
    wrapper_paths = [
        REPO_ROOT / "AGENTS.md",
        REPO_ROOT / "static" / "AGENTS.md",
    ]

    missing = [p for p in wrapper_paths if not p.exists()]
    assert not missing, "Missing AGENTS wrapper files:\n" + "\n".join(str(p) for p in missing)

    bad: list[str] = []
    for p in wrapper_paths:
        lines = _read_utf8(p).splitlines()
        if lines != [expected_line]:
            bad.append(f"{p.relative_to(REPO_ROOT)}: expected exactly `{expected_line}`")

    assert not bad, "AGENTS wrappers must be one-line pointers:\n" + "\n".join(bad)


def test_shipped_templates_use_namespaced_gardening_commands() -> None:
    """
    Guardrail: shipped templates must reference gardening automation via the plugin namespace.

    This avoids ambiguity ("which command ran?") and prevents shipping thin local wrappers.
    """
    roots = [
        REPO_ROOT / "static" / "memory_bank",
        REPO_ROOT / "static" / "commands",
        REPO_ROOT / "static" / "agents",
        REPO_ROOT / "static" / "skills",
        REPO_ROOT / "prompts" / "memory_bank",
    ]

    offenders: list[str] = []
    for root in roots:
        if not root.exists():
            continue

        for md_file in root.rglob("*.md"):
            content = _read_utf8(md_file)
            if any(
                s in content
                for s in [
                    "/fix-broken-links",
                    "/optimize-memory-bank",
                ]
            ):
                rel = md_file.relative_to(REPO_ROOT)
                offenders.append(str(rel))

    assert not offenders, (
        "Shipped templates must not reference unnamespaced gardening commands:\n"
        + "\n".join(f"- {p}" for p in offenders)
    )


def test_prompt_output_paths_match_prompt_locations() -> None:
    """
    Guardrail: prompt-generated files must mirror prompt paths.

    Convention:
    - prompts/memory_bank/<path>/<name>.md.prompt -> .memory_bank/<path>/<name>.md
    - prompts/<name>.md.prompt -> <name>.md (repo root)
    """
    prompts_root = REPO_ROOT / "prompts"
    assert prompts_root.exists(), f"Missing prompts dir: {prompts_root}"

    def parse_frontmatter(prompt_file: Path) -> tuple[str, str] | None:
        lines = _read_utf8(prompt_file).splitlines()
        if not lines or lines[0].strip() != "---":
            return None

        file_name: str | None = None
        target_path: str | None = None

        for line in lines[1:]:
            if line.strip() == "---":
                break

            if line.startswith("file:"):
                file_name = line.split(":", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("target_path:"):
                target_path = line.split(":", 1)[1].strip().strip('"').strip("'")

        if not file_name or not target_path:
            return None

        return file_name, target_path

    mismatches: list[str] = []
    for prompt_file in sorted(prompts_root.rglob("*.prompt")):
        rel_prompt = prompt_file.relative_to(prompts_root).as_posix()
        if not rel_prompt.endswith(".prompt"):
            continue

        frontmatter = parse_frontmatter(prompt_file)
        if frontmatter is None:
            mismatches.append(f"{prompt_file.relative_to(REPO_ROOT)}: missing/invalid frontmatter")
            continue

        file_name, target_path = frontmatter

        # Expected output path based on prompt location.
        rel_no_prompt = rel_prompt.removesuffix(".prompt")
        if rel_no_prompt.startswith("memory_bank/"):
            expected_out = ".memory_bank/" + rel_no_prompt.removeprefix("memory_bank/")
        else:
            expected_out = rel_no_prompt

        # Actual output path based on frontmatter.
        actual_out = (Path(target_path) / file_name).as_posix()

        # Normalize: drop leading "./" for stable comparisons.
        if actual_out.startswith("./"):
            actual_out = actual_out[2:]
        if expected_out.startswith("./"):
            expected_out = expected_out[2:]

        if actual_out != expected_out:
            mismatches.append(
                f"{prompt_file.relative_to(REPO_ROOT)}: expected `{expected_out}` but frontmatter maps to `{actual_out}`"
            )

        # Extra sanity check: file field should match the prompt basename (without `.prompt`).
        expected_file_name = Path(rel_no_prompt).name
        if file_name != expected_file_name:
            mismatches.append(
                f"{prompt_file.relative_to(REPO_ROOT)}: expected `file: {expected_file_name}` but found `file: {file_name}`"
            )

    assert not mismatches, "Prompt path/output mapping drift:\n" + "\n".join(mismatches)


# ============ Helper function unit tests ============


class TestStripFencedCodeBlocks:
    def test_removes_fenced_block(self):
        md = "before\n```python\nprint('hello')\n```\nafter"
        result = _strip_fenced_code_blocks(md)
        assert "print" not in result
        assert "before" in result
        assert "after" in result

    def test_preserves_non_fenced_content(self):
        md = "line 1\nline 2\nline 3"
        assert _strip_fenced_code_blocks(md) == md

    def test_handles_quadruple_backtick_fence(self):
        md = "before\n````\ncode\n````\nafter"
        result = _strip_fenced_code_blocks(md)
        assert "code" not in result
        assert "before" in result
        assert "after" in result

    def test_empty_input(self):
        assert _strip_fenced_code_blocks("") == ""

    def test_nested_shorter_fence_not_closed_early(self):
        md = "before\n````\n```\nnested\n```\n````\nafter"
        result = _strip_fenced_code_blocks(md)
        assert "nested" not in result
        assert "after" in result


class TestStripInlineCode:
    def test_removes_inline_code(self):
        md = "Use `foo()` to do things."
        result = _strip_inline_code(md)
        assert "foo()" not in result
        assert "Use" in result
        assert "to do things." in result

    def test_preserves_text_without_backticks(self):
        md = "No code here."
        assert _strip_inline_code(md) == md

    def test_multiple_inline_codes(self):
        md = "Call `a()` then `b()`."
        result = _strip_inline_code(md)
        assert "a()" not in result
        assert "b()" not in result
        assert "Call" in result

    def test_empty_input(self):
        assert _strip_inline_code("") == ""


# ============ Competency file tests ============


def test_static_testing_competency_exists_and_is_concise() -> None:
    """
    The testing competency must be a static file (not prompt-generated)
    with universal rules only, targeting 70-90 lines.
    """
    testing_md = COMPETENCIES_DIR / "testing.md"
    assert testing_md.exists(), f"Missing static testing competency: {testing_md}"

    content = testing_md.read_text(encoding="utf-8")
    line_count = len(content.splitlines())
    assert 50 <= line_count <= 120, (
        f"testing.md should be 70-90 lines (got {line_count})"
    )

    # Must have key sections
    assert "# " in content, "testing.md must have a heading"
    assert "Severity" in content, "testing.md must define severity levels"


def test_testing_platform_files_exist() -> None:
    """Platform-specific testing competency files must exist."""
    platforms_dir = COMPETENCIES_DIR / "testing-platforms"
    assert (platforms_dir / "pytest.md").exists(), "Missing pytest.md platform file"
    assert (platforms_dir / "jest.md").exists(), "Missing jest.md platform file"

