import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

WORKFLOWS_DIR = REPO_ROOT / "static" / "memory_bank" / "workflows"
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


def _expected_workflow_relpaths() -> set[str]:
    """
    Relative paths (posix) under `.memory_bank/workflows/` that are expected to
    exist in generated projects, coming from:
    - static workflow files
    - prompt-generated workflow files (e.g., review/testing.md)
    """
    expected: set[str] = set()

    # Static workflow files (always shipped)
    for md_file in _iter_md_files(WORKFLOWS_DIR):
        expected.add(md_file.relative_to(WORKFLOWS_DIR).as_posix())

    # Prompt-generated workflow files (conditional, but valid targets)
    for prompt_file in sorted((REPO_ROOT / "prompts").rglob("*.prompt")):
        text = _read_utf8(prompt_file)
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            continue

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
            continue

        if not target_path.startswith(".memory_bank/workflows/"):
            continue

        # target_path includes trailing slash in our schema; handle either way.
        rel_dir = target_path.removeprefix(".memory_bank/workflows/").lstrip("/")
        rel_path = (Path(rel_dir) / file_name).as_posix()
        expected.add(rel_path)

    return expected


def _iter_md_files(root: Path) -> list[Path]:
    return sorted([p for p in root.rglob("*.md") if p.is_file()])


def test_static_workflows_internal_relative_links_resolve() -> None:
    """
    Mechanical guardrail: links between static workflow files must not drift.

    We only validate markdown links that resolve *within* static workflows/ tree.
    Links to guides/ or other generated docs are intentionally excluded.
    """
    assert WORKFLOWS_DIR.exists(), f"Missing workflows dir: {WORKFLOWS_DIR}"

    link_re = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    expected = _expected_workflow_relpaths()

    broken: list[str] = []
    for md_file in _iter_md_files(WORKFLOWS_DIR):
        content = _strip_inline_code(_strip_fenced_code_blocks(_read_utf8(md_file)))
        for _, link_target in link_re.findall(content):
            link_target = link_target.split("#", 1)[0].strip()
            if not link_target:
                continue

            if link_target.startswith(("http://", "https://", "mailto:", "#")):
                continue

            # Absolute-from-repo links aren’t used in these static workflows today.
            if link_target.startswith("/"):
                continue

            resolved = (md_file.parent / link_target).resolve()
            try:
                rel = resolved.relative_to(WORKFLOWS_DIR).as_posix()
            except ValueError:
                # Outside workflows/ (e.g., ../guides/...) -> don’t validate here.
                continue

            if resolved.exists():
                continue

            # Allow links to prompt-generated workflow files (conditional but valid targets).
            if rel in expected:
                continue

            # Otherwise: drift/typo.
            if not resolved.exists():
                rel_source = md_file.relative_to(REPO_ROOT)
                rel_target = resolved.relative_to(REPO_ROOT)
                broken.append(f"{rel_source}: ({link_target}) -> {rel_target}")

    assert not broken, "Broken internal workflow links:\n" + "\n".join(broken)


def test_static_workflow_path_references_exist() -> None:
    """
    Mechanical guardrail: any explicit `.memory_bank/workflows/<file>.md` reference
    in static templates must point to a workflow file we actually ship.
    """
    assert WORKFLOWS_DIR.exists(), f"Missing workflows dir: {WORKFLOWS_DIR}"

    workflow_ref_re = re.compile(r"\.memory_bank/workflows/([A-Za-z0-9_\-./]+\.md)")
    expected = _expected_workflow_relpaths()

    search_roots = [
        WORKFLOWS_DIR,
        STATIC_COMMANDS_DIR,
        STATIC_SKILLS_DIR,
    ]

    missing: list[str] = []
    for root in search_roots:
        if not root.exists():
            continue

        for md_file in _iter_md_files(root):
            content = _read_utf8(md_file)
            for rel_target in workflow_ref_re.findall(content):
                if rel_target in expected:
                    continue

                target_path = (WORKFLOWS_DIR / Path(rel_target)).resolve()
                rel_source = md_file.relative_to(REPO_ROOT)
                rel_target_repo = target_path.relative_to(REPO_ROOT)
                missing.append(
                    f"{rel_source}: .memory_bank/workflows/{rel_target} -> {rel_target_repo} (unknown workflow target)"
                )

    assert not missing, "Missing referenced workflow files:\n" + "\n".join(missing)


def test_readme_prompt_lists_only_shipped_commands() -> None:
    """
    The generated `.memory_bank/README.md` is the primary navigation hub.
    Its command list must not drift from what we actually deploy.
    """
    shipped_commands = {p.stem for p in STATIC_COMMANDS_DIR.glob("*.md")}
    assert shipped_commands, f"No static commands found in: {STATIC_COMMANDS_DIR}"

    content = _read_utf8(README_PROMPT_PATH)

    # Extract slash command names from backticked command strings like:
    # ` /create-protocol [args] `
    cmd_name_re = re.compile(r"`/([a-z0-9-]+)")
    mentioned = set(cmd_name_re.findall(content))

    unknown = sorted([c for c in mentioned if c not in shipped_commands])
    assert not unknown, (
        "README prompt mentions commands we don't ship:\n"
        + "\n".join(f"- /{c}" for c in unknown)
        + "\n\nShipped commands:\n"
        + "\n".join(f"- /{c}" for c in sorted(shipped_commands))
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

