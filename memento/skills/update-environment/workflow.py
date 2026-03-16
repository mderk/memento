"""Update-environment workflow: selective update of Memory Bank files.

Detects tech stack changes, plugin updates, local modifications.
Applies 3-way merge to preserve user edits during regeneration.
"""

from pathlib import Path


def _has_changes(ctx) -> bool:
    """Check if pre-update detected any changes worth acting on."""
    pre = ctx.variables.get("pre_update")
    if not pre:
        return False
    s = pre.get("summary", {})
    return any(s.get(k, 0) > 0 for k in (
        "local_modified", "source_changed", "new_prompts", "obsolete",
        "static_new", "static_safe_overwrite", "static_merge_needed",
    ))

# Copy clean file to target (for new files that don't need merge)
_COPY_TO_TARGET_CMD = (
    'mkdir -p "$(dirname {{variables.current_file.target}})" && '
    'cp {{variables.clean_dir}}/{{variables.current_file.target}} {{variables.current_file.target}}'
)


WORKFLOW = WorkflowDef(
    name="update-environment",
    description="Update Memory Bank files after tech stack changes or plugin updates",
    blocks=[
        # ── Phase 0: Detect changes ──────────────────────────────────
        ShellStep(
            name="check-context",
            command="test -f {{cwd}}/.memory_bank/project-analysis.json "
                    "&& test -f {{cwd}}/.memory_bank/generation-plan.md "
                    "&& echo '{\"exists\": true}' || echo '{\"exists\": false}'",
            result_var="context_check",
        ),

        ShellStep(
            name="detect-stack",
            command="python3 {{variables.plugin_root}}/skills/detect-tech-stack/scripts/detect.py "
                    "--output /tmp/new-project-analysis.json",
            condition=lambda ctx: ctx.variables.get("context_check", {}).get("exists", False),
        ),

        # ── Recommend missing dev tools ──────────────────────────────
        ShellStep(
            name="check-recommendations",
            command="python3 {{variables.plugin_root}}/skills/detect-tech-stack/scripts/detect.py "
                    "--recommendations /tmp/new-project-analysis.json",
            result_var="tool_recommendations",
            condition=lambda ctx: ctx.variables.get("context_check", {}).get("exists", False),
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
                    "--output /tmp/new-project-analysis.json",
            condition=lambda ctx: ctx.variables.get("install_tools") == "yes",
        ),

        ShellStep(
            name="pre-update",
            command="python3 {{variables.plugin_root}}/skills/analyze-local-changes/scripts/analyze.py "
                    "pre-update --plugin-root {{variables.plugin_root}} "
                    "--new-analysis /tmp/new-project-analysis.json",
            result_var="pre_update",
            condition=lambda ctx: ctx.variables.get("context_check", {}).get("exists", False),
        ),

        PromptStep(
            name="action",
            prompt_type="choice",
            message="Pre-update analysis complete.\n"
                    "Source changed: {{variables.pre_update.summary.source_changed}}, "
                    "Statics to update: {{variables.pre_update.summary.static_safe_overwrite}}, "
                    "Statics to merge: {{variables.pre_update.summary.static_merge_needed}}, "
                    "New statics: {{variables.pre_update.summary.static_new}}, "
                    "New prompts: {{variables.pre_update.summary.new_prompts}}, "
                    "Local modified: {{variables.pre_update.summary.local_modified}}, "
                    "Obsolete: {{variables.pre_update.summary.obsolete}}\n"
                    "Choose action:",
            options=[
                "Update affected files only",
                "Add new prompts only",
                "Update static files",
                "Delete obsolete files",
                "All updates",
                "Full regeneration",
            ],
            default="All updates",
            result_var="action",
            condition=_has_changes,
        ),

        # ── Phase 1: Update project-analysis.json ────────────────────
        ShellStep(
            name="update-analysis",
            command="cp {{cwd}}/.memory_bank/project-analysis.json "
                    "{{cwd}}/.memory_bank/project-analysis.json.backup "
                    "&& cp /tmp/new-project-analysis.json "
                    "{{cwd}}/.memory_bank/project-analysis.json",
            condition=lambda ctx: ctx.variables.get("action") is not None,
        ),

        ShellStep(
            name="build-plan",
            command="python3 {{variables.plugin_root}}/skills/analyze-local-changes/scripts/analyze.py "
                    "plan-generation --plugin-root {{variables.plugin_root}} "
                    "--analysis {{cwd}}/.memory_bank/project-analysis.json",
            result_var="generation_plan",
            condition=lambda ctx: ctx.variables.get("action") == "Full regeneration",
        ),

        ShellStep(
            name="build-plan-changed",
            command="python3 {{variables.plugin_root}}/skills/analyze-local-changes/scripts/analyze.py "
                    "plan-generation --plugin-root {{variables.plugin_root}} "
                    "--analysis {{cwd}}/.memory_bank/project-analysis.json "
                    "--only-changed",
            result_var="generation_plan",
            condition=lambda ctx: ctx.variables.get("action") in (
                "All updates", "Update affected files only",
            ),
        ),

        PromptStep(
            name="confirm",
            prompt_type="confirm",
            message="Ready to proceed with: {{variables.action}}. Continue?",
            default="yes",
            result_var="confirmed",
            condition=lambda ctx: ctx.variables.get("action") is not None,
        ),

        # ── Phase 2: Execute update strategy ─────────────────────────
        ConditionalBlock(
            name="execute-update",
            condition=lambda ctx: ctx.variables.get("confirmed") == "yes",
            branches=[
                # ── Delete obsolete only ──
                # (handled by top-level clean-obsolete step after ConditionalBlock)
                Branch(
                    condition=lambda ctx: ctx.variables.get("action") == "Delete obsolete files",
                    blocks=[],
                ),
                # ── Add new prompts only ──
                Branch(
                    condition=lambda ctx: ctx.variables.get("action") == "Add new prompts only",
                    blocks=[
                        ParallelEachBlock(
                            name="generate-new",
                            parallel_for="variables.pre_update.new_prompts",
                            item_var="current_file",
                            template=[
                                LLMStep(
                                    name="generate-file",
                                    prompt="02-generate.md",
                                    tools=["Read", "Write", "Glob", "Grep"],
                                ),
                                ShellStep(
                                    name="copy-to-target",
                                    command=_COPY_TO_TARGET_CMD,
                                ),
                            ],
                        ),
                    ],
                ),
                # ── Update static files only ──
                Branch(
                    condition=lambda ctx: ctx.variables.get("action") == "Update static files",
                    blocks=[
                        ShellStep(
                            name="copy-static-update",
                            command="python3 {{variables.plugin_root}}/skills/analyze-local-changes/scripts/analyze.py "
                                    "copy-static --plugin-root {{variables.plugin_root}} "
                                    "--clean-dir {{variables.clean_dir}} "
                                    "--filter new,safe_overwrite,merge_needed",
                            result_var="static_results",
                        ),
                    ],
                ),
            ],
            # ── Default: All updates / Full regeneration / Affected only ──
            default=[
                ShellStep(
                    name="copy-static-all",
                    command="python3 {{variables.plugin_root}}/skills/analyze-local-changes/scripts/analyze.py "
                            "copy-static --plugin-root {{variables.plugin_root}} "
                            "--clean-dir {{variables.clean_dir}} "
                            "--filter new,safe_overwrite,merge_needed",
                    result_var="static_results",
                ),
                ParallelEachBlock(
                    name="regenerate-files",
                    parallel_for="variables.generation_plan.prompt_items",
                    item_var="current_file",
                    max_concurrency=5,
                    template=[
                        LLMStep(
                            name="generate-file",
                            prompt="02-generate.md",
                            tools=["Read", "Write", "Glob", "Grep"],
                        ),
                        ShellStep(
                            name="merge-file",
                            command="python3 {{variables.plugin_root}}/skills/analyze-local-changes/scripts/analyze.py "
                                    "merge {{variables.current_file.target}} "
                                    "--base-commit {{variables.pre_update.base_commit}} "
                                    "--new-file {{variables.clean_dir}}/{{variables.current_file.target}} "
                                    "--write",
                            condition=lambda ctx: (
                                Path(ctx.get_var("variables.current_file.target") or "").exists()
                                and ctx.get_var("variables.pre_update.base_commit")
                            ),
                        ),
                        # Copy clean file to target for new files (merge-file skipped when target doesn't exist)
                        ShellStep(
                            name="copy-to-target",
                            command=_COPY_TO_TARGET_CMD,
                            condition=lambda ctx: (
                                not Path(ctx.get_var("variables.current_file.target") or "").exists()
                            ),
                        ),
                    ],
                ),
                LoopBlock(
                    name="update-plan-entries",
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

        # Clean obsolete files + plan entries (runs for any update action)
        ShellStep(
            name="clean-obsolete",
            command="python3 {{variables.plugin_root}}/skills/analyze-local-changes/scripts/analyze.py "
                    "clean-obsolete --plugin-root {{variables.plugin_root}}",
            condition=lambda ctx: (
                ctx.variables.get("confirmed") == "yes"
                and bool(ctx.variables.get("pre_update", {}).get("obsolete_files"))
            ),
        ),

        # ── Phase 3: Finalize ────────────────────────────────────────
        ShellStep(
            name="fix-links",
            command="python3 {{variables.plugin_root}}/skills/fix-broken-links/scripts/validate-memory-bank-links.py",
            condition=lambda ctx: ctx.variables.get("confirmed") == "yes",
        ),

        ShellStep(
            name="redundancy-check",
            command="python3 {{variables.plugin_root}}/skills/check-redundancy/scripts/check-redundancy.py "
                    "{{cwd}}/.memory_bank/generation-plan.md",
            condition=lambda ctx: (
                ctx.variables.get("confirmed") == "yes"
                and Path(ctx.cwd + "/.memory_bank/generation-plan.md").exists()
            ),
        ),

        ShellStep(
            name="commit-generation",
            command="python3 {{variables.plugin_root}}/skills/analyze-local-changes/scripts/analyze.py "
                    "commit-generation --plugin-version {{variables.plugin_version}} "
                    "--clean-dir {{variables.clean_dir}}",
            condition=lambda ctx: ctx.variables.get("confirmed") == "yes",
        ),
    ],
)
