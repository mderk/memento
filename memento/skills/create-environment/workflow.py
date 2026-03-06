"""Create-environment workflow: generate Memory Bank documentation for a project.

Supports three strategies:
- Fresh: clean generation (default for first run)
- Resume: generate only missing files from existing plan
- Regenerate with merge: full regen + 3-way merge with local changes
"""

from pathlib import Path

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
                            template=[
                                LLMStep(
                                    name="generate-file",
                                    prompt="01-generate.md",
                                    tools=["Read", "Write", "Glob", "Grep"],
                                )
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
                                    "--clean-dir /tmp/memento-clean "
                                    "--base-commit {{variables.existing_env.base_commit}}",
                            result_var="static_results",
                        ),
                        LoopBlock(
                            name="generate-merge",
                            loop_over="variables.generation_plan.prompt_items",
                            loop_var="current_file",
                            blocks=[
                                LLMStep(
                                    name="generate-file",
                                    prompt="02-generate-merge.md",
                                    tools=["Read", "Write", "Glob", "Grep"],
                                ),
                                ShellStep(
                                    name="merge-file",
                                    command="python3 {{variables.plugin_root}}/skills/analyze-local-changes/scripts/analyze.py "
                                            "merge {{variables.current_file.target}} "
                                            "--base-commit {{variables.existing_env.base_commit}} "
                                            "--new-file /tmp/memento-clean/{{variables.current_file.target}} "
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
                            "--clean-dir /tmp/memento-clean",
                    result_var="static_results",
                ),
                ParallelEachBlock(
                    name="generate-fresh",
                    parallel_for="variables.generation_plan.prompt_items",
                    template=[
                        LLMStep(
                            name="generate-file",
                            prompt="01-generate.md",
                            tools=["Read", "Write", "Glob", "Grep"],
                        )
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
