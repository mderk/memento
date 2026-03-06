"""Update-environment workflow: selective update of Memory Bank files.

Detects tech stack changes, plugin updates, local modifications.
Applies 3-way merge to preserve user edits during regeneration.
"""

from pathlib import Path

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
                    "Local modified: {{variables.pre_update.summary.local_modified}}, "
                    "Source changed: {{variables.pre_update.summary.source_changed}}, "
                    "New prompts: {{variables.pre_update.summary.new_prompts}}, "
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
            condition=lambda ctx: ctx.variables.get("pre_update") is not None,
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
            condition=lambda ctx: ctx.variables.get("action") in (
                "Full regeneration", "All updates", "Update affected files only",
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
            condition=lambda ctx: ctx.variables.get("confirmed", "yes") == "yes",
            branches=[
                # ── Delete obsolete only ──
                Branch(
                    condition=lambda ctx: ctx.variables.get("action") == "Delete obsolete files",
                    blocks=[
                        LLMStep(
                            name="delete-obsolete",
                            prompt="01-delete-obsolete.md",
                            tools=["Read", "Write", "Bash", "Glob"],
                        ),
                    ],
                ),
                # ── Add new prompts only ──
                Branch(
                    condition=lambda ctx: ctx.variables.get("action") == "Add new prompts only",
                    blocks=[
                        ParallelEachBlock(
                            name="generate-new",
                            parallel_for="variables.pre_update.new_prompts",
                            template=[
                                LLMStep(
                                    name="generate-file",
                                    prompt="02-generate.md",
                                    tools=["Read", "Write", "Glob", "Grep"],
                                )
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
                                    "--clean-dir /tmp/memento-clean "
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
                            "--clean-dir /tmp/memento-clean "
                            "--filter new,safe_overwrite,merge_needed",
                    result_var="static_results",
                ),
                LoopBlock(
                    name="regenerate-files",
                    loop_over="variables.generation_plan.prompt_items",
                    loop_var="current_file",
                    blocks=[
                        LLMStep(
                            name="generate-file",
                            prompt="02-generate.md",
                            tools=["Read", "Write", "Glob", "Grep"],
                        ),
                        ShellStep(
                            name="merge-file",
                            command="python3 {{variables.plugin_root}}/skills/analyze-local-changes/scripts/analyze.py "
                                    "merge {{variables.current_file.target}} "
                                    "--new-file /tmp/memento-clean/{{variables.current_file.target}} "
                                    "--write",
                            condition=lambda ctx: (
                                Path(ctx.get_var("variables.current_file.target") or "").exists()
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

        # ── Phase 3: Finalize ────────────────────────────────────────
        ShellStep(
            name="fix-links",
            command="python3 {{variables.plugin_root}}/skills/fix-broken-links/scripts/validate-memory-bank-links.py "
                    "--memory-bank {{cwd}}/.memory_bank",
            condition=lambda ctx: ctx.variables.get("confirmed", "yes") == "yes",
        ),

        ShellStep(
            name="redundancy-check",
            command="python3 {{variables.plugin_root}}/skills/check-redundancy/scripts/check-redundancy.py "
                    "--memory-bank {{cwd}}/.memory_bank --threshold 10",
            condition=lambda ctx: ctx.variables.get("confirmed", "yes") == "yes",
        ),

        ShellStep(
            name="commit-generation",
            command="python3 {{variables.plugin_root}}/skills/analyze-local-changes/scripts/analyze.py "
                    "commit-generation --plugin-version {{variables.plugin_version}} "
                    "--clean-dir /tmp/memento-clean",
            condition=lambda ctx: ctx.variables.get("confirmed", "yes") == "yes",
        ),
    ],
)
