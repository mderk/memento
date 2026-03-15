"""Create-environment workflow: generate Memory Bank documentation for a project.

Supports three strategies:
- Fresh: clean generation (default for first run)
- Resume: generate only missing files from existing plan
- Regenerate with merge: full regen + 3-way merge with local changes
"""

from pathlib import Path

# Template for writing generated content via tee (stdin → both targets)
_WRITE_CMD = (
    'mkdir -p "$(dirname {{variables.item.target}})" '
    '"$(dirname {{variables.clean_dir}}/{{variables.item.target}})" && '
    'tee {{variables.clean_dir}}/{{variables.item.target}} > {{variables.item.target}}'
)

# Template for merge workflow (writes only to clean dir, merge step handles target)
_WRITE_CLEAN_CMD = (
    'mkdir -p "$(dirname {{variables.clean_dir}}/{{variables.current_file.target}})" && '
    'cat > {{variables.clean_dir}}/{{variables.current_file.target}}'
)

WORKFLOW = WorkflowDef(
    name="create-environment",
    description="Generate a comprehensive AI-friendly development environment",
    blocks=[
        # ── Phase 0: Check existing environment ──────────────────────
        ShellStep(
            name="check-existing",
            command="python3 {{variables.plugin_root}}/skills/analyze-local-changes/scripts/analyze.py "
                    "check-existing --memory-bank {{cwd}}/.memory_bank",
            result_var="existing_env",
        ),

        PromptStep(
            name="strategy",
            prompt_type="choice",
            message="Existing environment found ({{variables.existing_env.total_files}} files, "
                    "{{variables.existing_env.modified_count}} modified).\nChoose strategy:",
            options=["Resume (generate missing only)", "Regenerate with merge", "Regenerate fresh"],
            default="Regenerate fresh",
            result_var="strategy",
            condition=lambda ctx: ctx.variables.get("existing_env", {}).get("exists", False),
        ),

        # ── Phase 1: Detect tech stack + build plan ──────────────────
        ShellStep(
            name="ensure-dirs",
            command="mkdir -p {{cwd}}/.memory_bank",
            condition=lambda ctx: ctx.variables.get("strategy") != "Resume (generate missing only)",
        ),

        ShellStep(
            name="detect-stack",
            command="python3 {{variables.plugin_root}}/skills/detect-tech-stack/scripts/detect.py "
                    "--output {{cwd}}/.memory_bank/project-analysis.json",
            condition=lambda ctx: ctx.variables.get("strategy") != "Resume (generate missing only)",
        ),

        # ── Recommend missing dev tools ──────────────────────────────
        ShellStep(
            name="check-recommendations",
            command="python3 {{variables.plugin_root}}/skills/detect-tech-stack/scripts/detect.py "
                    "recommendations {{cwd}}/.memory_bank/project-analysis.json",
            result_var="tool_recommendations",
            condition=lambda ctx: ctx.variables.get("strategy") != "Resume (generate missing only)",
        ),

        PromptStep(
            name="install-tools",
            prompt_type="confirm",
            message="Missing dev tools detected:\n{{variables.tool_recommendations.display}}\n\nInstall recommended tools?",
            default="yes",
            result_var="install_tools",
            condition=lambda ctx: bool(ctx.variables.get("tool_recommendations", {}).get("tools")),
        ),

        LLMStep(
            name="setup-tools",
            prompt_text=(
                "Install the following recommended dev tools for this project:\n\n"
                "{{variables.tool_recommendations.display}}\n\n"
                "For each tool:\n"
                "1. Run the install command\n"
                "2. Add minimal default configuration if needed "
                "(e.g. a `[tool.ruff]` section in pyproject.toml)\n"
                "3. Verify it works by running `<tool> --version` or equivalent\n\n"
                "Do NOT run linting/formatting fixes — just install and configure.\n"
                "IMPORTANT: Use the exact install commands shown above — "
                "they match the project's declared package manager."
            ),
            tools=["Read", "Write", "Edit", "Bash"],
            condition=lambda ctx: ctx.variables.get("install_tools") == "yes",
        ),

        ShellStep(
            name="re-detect-stack",
            command="python3 {{variables.plugin_root}}/skills/detect-tech-stack/scripts/detect.py "
                    "--output {{cwd}}/.memory_bank/project-analysis.json",
            condition=lambda ctx: ctx.variables.get("install_tools") == "yes",
        ),

        ShellStep(
            name="create-plan",
            command="python3 {{variables.plugin_root}}/skills/analyze-local-changes/scripts/analyze.py "
                    "plan-generation --plugin-root {{variables.plugin_root}} "
                    "--analysis {{cwd}}/.memory_bank/project-analysis.json",
            result_var="generation_plan",
            condition=lambda ctx: ctx.variables.get("strategy") != "Resume (generate missing only)",
        ),

        PromptStep(
            name="confirm",
            prompt_type="confirm",
            message="Generation plan: {{variables.generation_plan.prompts}} prompts + "
                    "{{variables.generation_plan.statics}} static files "
                    "({{variables.generation_plan.total}} total). Proceed?",
            default="yes",
            result_var="confirmed",
            condition=lambda ctx: ctx.variables.get("generation_plan") is not None,
        ),

        # ── Phase 2: Strategy branching ──────────────────────────────
        ConditionalBlock(
            name="execute-strategy",
            condition=lambda ctx: ctx.variables.get("confirmed", "yes") == "yes",
            branches=[
                # ── Resume strategy ──
                Branch(
                    condition=lambda ctx: ctx.variables.get("strategy") == "Resume (generate missing only)",
                    blocks=[
                        ShellStep(
                            name="load-existing-plan",
                            command="python3 {{variables.plugin_root}}/skills/analyze-local-changes/scripts/analyze.py "
                                    "plan-generation --plugin-root {{variables.plugin_root}} "
                                    "--analysis {{cwd}}/.memory_bank/project-analysis.json",
                            result_var="generation_plan",
                        ),
                        ParallelEachBlock(
                            name="generate-missing",
                            parallel_for="variables.generation_plan.prompt_items",
                            max_concurrency=5,
                            template=[
                                LLMStep(
                                    name="generate-file",
                                    prompt="01-generate.md",
                                    tools=["Read", "Glob", "Grep"],
                                ),
                                ShellStep(
                                    name="write-file",
                                    command=_WRITE_CMD,
                                    stdin="results.generate-file.output",
                                ),
                            ],
                        ),
                    ],
                ),
                # ── Merge strategy ──
                Branch(
                    condition=lambda ctx: ctx.variables.get("strategy") == "Regenerate with merge",
                    blocks=[
                        ShellStep(
                            name="copy-static-merge",
                            command="python3 {{variables.plugin_root}}/skills/analyze-local-changes/scripts/analyze.py "
                                    "copy-static --plugin-root {{variables.plugin_root}} "
                                    "--clean-dir {{variables.clean_dir}} "
                                    "--base-commit {{variables.existing_env.base_commit}}",
                            result_var="static_results",
                        ),
                        ParallelEachBlock(
                            name="generate-merge",
                            parallel_for="variables.generation_plan.prompt_items",
                            item_var="current_file",
                            max_concurrency=5,
                            template=[
                                LLMStep(
                                    name="generate-file",
                                    prompt="02-generate-merge.md",
                                    tools=["Read", "Glob", "Grep"],
                                ),
                                ShellStep(
                                    name="write-clean",
                                    command=_WRITE_CLEAN_CMD,
                                    stdin="results.generate-file.output",
                                ),
                                ShellStep(
                                    name="merge-file",
                                    command="python3 {{variables.plugin_root}}/skills/analyze-local-changes/scripts/analyze.py "
                                            "merge {{variables.current_file.target}} "
                                            "--base-commit {{variables.existing_env.base_commit}} "
                                            "--new-file {{variables.clean_dir}}/{{variables.current_file.target}} "
                                            "--write",
                                ),
                            ],
                        ),
                        LoopBlock(
                            name="update-plan-merge",
                            loop_over="variables.generation_plan.plan",
                            loop_var="plan_item",
                            blocks=[
                                ShellStep(
                                    name="update-plan-entry",
                                    command="python3 {{variables.plugin_root}}/skills/analyze-local-changes/scripts/analyze.py "
                                            "update-plan {{variables.plan_item.target}} "
                                            "--plugin-root {{variables.plugin_root}}",
                                    condition=lambda ctx: (
                                        Path(ctx.get_var("variables.plan_item.target") or "").exists()
                                    ),
                                ),
                            ],
                        ),
                    ],
                ),
            ],
            # ── Default: Fresh strategy ──
            default=[
                ShellStep(
                    name="copy-static",
                    command="python3 {{variables.plugin_root}}/skills/analyze-local-changes/scripts/analyze.py "
                            "copy-static --plugin-root {{variables.plugin_root}} "
                            "--clean-dir {{variables.clean_dir}}",
                    result_var="static_results",
                ),
                ParallelEachBlock(
                    name="generate-fresh",
                    parallel_for="variables.generation_plan.prompt_items",
                    max_concurrency=5,
                    template=[
                        LLMStep(
                            name="generate-file",
                            prompt="01-generate.md",
                            tools=["Read", "Glob", "Grep"],
                        ),
                        ShellStep(
                            name="write-file",
                            command=_WRITE_CMD,
                            stdin="results.generate-file.output",
                        ),
                    ],
                ),
                LoopBlock(
                    name="update-plan-fresh",
                    loop_over="variables.generation_plan.plan",
                    loop_var="plan_item",
                    blocks=[
                        ShellStep(
                            name="update-plan-entry",
                            command="python3 {{variables.plugin_root}}/skills/analyze-local-changes/scripts/analyze.py "
                                    "update-plan {{variables.plan_item.target}} "
                                    "--plugin-root {{variables.plugin_root}}",
                            condition=lambda ctx: (
                                Path(ctx.get_var("variables.plan_item.target") or "").exists()
                            ),
                        ),
                    ],
                ),
            ],
        ),

        # ── Phase 3: Finalize ────────────────────────────────────────
        ShellStep(
            name="fix-links",
            command="python3 {{variables.plugin_root}}/skills/fix-broken-links/scripts/validate-memory-bank-links.py",
            condition=lambda ctx: ctx.variables.get("confirmed", "yes") == "yes",
        ),

        ShellStep(
            name="redundancy-check",
            command="python3 {{variables.plugin_root}}/skills/check-redundancy/scripts/check-redundancy.py "
                    "{{cwd}}/.memory_bank/generation-plan.md",
            condition=lambda ctx: (
                ctx.variables.get("confirmed", "yes") == "yes"
                and Path(ctx.cwd + "/.memory_bank/generation-plan.md").exists()
            ),
        ),

        ShellStep(
            name="commit-generation",
            command="python3 {{variables.plugin_root}}/skills/analyze-local-changes/scripts/analyze.py "
                    "commit-generation --plugin-version {{variables.plugin_version}} "
                    "--clean-dir {{variables.clean_dir}}",
            condition=lambda ctx: ctx.variables.get("confirmed", "yes") == "yes",
        ),
    ],
)
