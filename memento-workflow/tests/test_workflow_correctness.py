"""Tests for workflow correctness fixes (protocol 0003, step 01).

Verifies:
- code-review: load-competency has no result_var, command ends with '; true'
- code-review: 02-review.md uses results.load-competency.output (not variables.competency_rules)
- process-protocol: fix-review RetryBlock has condition checking has_blockers
- process-protocol: mark-plan-in-progress does not use 'git add -A'
"""

import importlib.util
import sys
import types as pytypes
from pathlib import Path

from conftest import _types_ns

# Load workflow modules dynamically using real engine types as _dsl
REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_WORKFLOWS = REPO_ROOT / "memento" / "static" / "workflows"


def _load_workflow_module(workflow_name: str):
    """Load a workflow.py module, injecting real engine types as _dsl."""
    wf_dir = STATIC_WORKFLOWS / workflow_name
    wf_file = wf_dir / "workflow.py"
    assert wf_file.exists(), f"Workflow file not found: {wf_file}"

    # Create a fake _dsl module from real engine types
    dsl_mod = pytypes.ModuleType("_dsl")
    for name, obj in _types_ns.items():
        setattr(dsl_mod, name, obj)
    sys.modules["_dsl"] = dsl_mod

    import typing
    orig = typing.TYPE_CHECKING
    typing.TYPE_CHECKING = True
    try:
        spec = importlib.util.spec_from_file_location(
            f"workflow_{workflow_name}", wf_file,
            submodule_search_locations=[str(wf_dir)],
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        typing.TYPE_CHECKING = orig
    return mod


class TestCodeReviewWorkflow:
    """Verify code-review workflow definition fixes."""

    def test_load_competency_has_no_result_var(self):
        """load-competency ShellStep must not have result_var (text output, not JSON)."""
        mod = _load_workflow_module("code-review")
        wf = mod.WORKFLOW

        # Find the ParallelEachBlock
        par_block = None
        for block in wf.blocks:
            if getattr(block, "name", "") == "reviews":
                par_block = block
                break
        assert par_block is not None, "ParallelEachBlock 'reviews' not found"

        # Find load-competency in the template
        load_step = None
        for step in par_block.template:
            if getattr(step, "name", "") == "load-competency":
                load_step = step
                break
        assert load_step is not None, "ShellStep 'load-competency' not found in template"
        assert not load_step.result_var, (
            f"load-competency should not have result_var (got '{load_step.result_var}'). "
            "Text output cannot be stored via result_var (requires JSON)."
        )

    def test_load_competency_command_always_succeeds(self):
        """load-competency command must end with '; true' to handle glob failures."""
        mod = _load_workflow_module("code-review")
        wf = mod.WORKFLOW

        par_block = next(b for b in wf.blocks if getattr(b, "name", "") == "reviews")
        load_step = next(s for s in par_block.template if getattr(s, "name", "") == "load-competency")

        assert load_step.command.rstrip().endswith("; true") or load_step.command.rstrip().endswith("|| true"), (
            f"load-competency command must end with '; true' or '|| true' to handle glob failures. "
            f"Got: ...{load_step.command[-30:]}"
        )

    def test_review_prompt_uses_results_output(self):
        """02-review.md must reference results.load-competency.output, not variables.competency_rules."""
        prompt_path = STATIC_WORKFLOWS / "code-review" / "prompts" / "02-review.md"
        assert prompt_path.exists(), f"Prompt not found: {prompt_path}"
        content = prompt_path.read_text()

        assert "variables.competency_rules" not in content, (
            "02-review.md still references {{variables.competency_rules}} — "
            "should use {{results.load-competency.output}}"
        )
        assert "results.load-competency.output" in content, (
            "02-review.md must reference {{results.load-competency.output}} "
            "to read shell step stdout"
        )


class TestProcessProtocolWorkflow:
    """Verify process-protocol workflow definition fixes."""

    def test_fix_review_has_condition(self):
        """fix-review RetryBlock must have a condition to skip when review is APPROVE."""
        mod = _load_workflow_module("process-protocol")
        wf = mod.WORKFLOW

        # Find the LoopBlock 'steps', then find fix-review inside
        loop_block = next(b for b in wf.blocks if getattr(b, "name", "") == "steps")
        fix_review = None
        for block in loop_block.blocks:
            if getattr(block, "name", "") == "fix-review":
                fix_review = block
                break

        assert fix_review is not None, "RetryBlock 'fix-review' not found in steps loop"
        assert fix_review.condition is not None, (
            "fix-review RetryBlock must have a condition to skip when review verdict is APPROVE"
        )

    def test_mark_plan_no_broad_git_add(self):
        """mark-plan-in-progress must not use 'git add -A' (too broad)."""
        mod = _load_workflow_module("process-protocol")
        wf = mod.WORKFLOW

        mark_step = None
        for block in wf.blocks:
            if getattr(block, "name", "") == "mark-plan-in-progress":
                mark_step = block
                break

        assert mark_step is not None, "ShellStep 'mark-plan-in-progress' not found"
        assert "git add -A" not in mark_step.command, (
            "mark-plan-in-progress uses 'git add -A' which stages all changes. "
            "Should scope to protocol directory only."
        )
