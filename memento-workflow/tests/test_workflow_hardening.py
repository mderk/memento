"""Tests for workflow engine hardening (protocol 0004).

Verifies:
- develop: coverage-retry has stagnation detection (save-prev-coverage + until condition)
- develop: acceptance-check uses variables.units (not variables.unit)
"""

import importlib.util
import sys
import types as pytypes
from pathlib import Path

from conftest import _types_ns

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_WORKFLOWS = REPO_ROOT / "memento" / "static" / "workflows"


def _load_workflow_module(workflow_name: str):
    """Load a workflow.py module, injecting real engine types as _dsl."""
    wf_dir = STATIC_WORKFLOWS / workflow_name
    wf_file = wf_dir / "workflow.py"
    assert wf_file.exists(), f"Workflow file not found: {wf_file}"

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
        sys.modules.pop("_dsl", None)
    return mod


def _find_block(blocks, name, block_type=None):
    """Recursively find a block by name in a block tree."""
    for block in blocks:
        if getattr(block, "name", "") == name:
            if block_type is None or block.type == block_type:
                return block
        # Search nested blocks
        for attr in ("blocks", "template"):
            nested = getattr(block, attr, None)
            if nested:
                found = _find_block(nested, name, block_type)
                if found:
                    return found
    return None


class TestCoverageStagnationDetection:
    """Verify coverage-retry RetryBlock has stagnation exit."""

    def test_save_prev_coverage_step_exists(self):
        """coverage-retry must contain a 'save-prev-coverage' step."""
        mod = _load_workflow_module("develop")
        wf = mod.WORKFLOW
        retry = _find_block(wf.blocks, "coverage-retry", "retry")
        assert retry is not None, "RetryBlock 'coverage-retry' not found"

        save_step = _find_block(retry.blocks, "save-prev-coverage")
        assert save_step is not None, (
            "ShellStep 'save-prev-coverage' not found in coverage-retry blocks. "
            "Needed to store previous coverage for stagnation detection."
        )

    def test_save_prev_coverage_sets_result_var(self):
        """save-prev-coverage must write to _prev_coverage variable."""
        mod = _load_workflow_module("develop")
        wf = mod.WORKFLOW
        retry = _find_block(wf.blocks, "coverage-retry", "retry")
        save_step = _find_block(retry.blocks, "save-prev-coverage")
        assert save_step is not None
        assert save_step.result_var == "_prev_coverage", (
            f"save-prev-coverage should set result_var='_prev_coverage', "
            f"got '{save_step.result_var}'"
        )

    def test_until_exits_on_stagnation(self):
        """coverage-retry until condition must exit when coverage doesn't change."""
        mod = _load_workflow_module("develop")
        wf = mod.WORKFLOW
        retry = _find_block(wf.blocks, "coverage-retry", "retry")
        assert retry is not None

        # Build mock context: coverage has gaps but _prev_coverage matches current
        WorkflowContext = _types_ns["WorkflowContext"]
        ctx = WorkflowContext(variables={
            "coverage": {"has_gaps": True, "overall_coverage": 50.0},
            "_prev_coverage": 50.0,
        })
        assert retry.until(ctx) is True, (
            "until should return True (exit) when _prev_coverage == overall_coverage"
        )

    def test_until_continues_when_coverage_improves(self):
        """coverage-retry should continue when coverage improved."""
        mod = _load_workflow_module("develop")
        wf = mod.WORKFLOW
        retry = _find_block(wf.blocks, "coverage-retry", "retry")

        WorkflowContext = _types_ns["WorkflowContext"]
        ctx = WorkflowContext(variables={
            "coverage": {"has_gaps": True, "overall_coverage": 60.0},
            "_prev_coverage": 50.0,
        })
        assert retry.until(ctx) is False, (
            "until should return False (continue) when coverage improved"
        )

    def test_until_continues_on_first_attempt(self):
        """First attempt has no _prev_coverage — should not exit on None == None."""
        mod = _load_workflow_module("develop")
        wf = mod.WORKFLOW
        retry = _find_block(wf.blocks, "coverage-retry", "retry")

        WorkflowContext = _types_ns["WorkflowContext"]
        ctx = WorkflowContext(variables={
            "coverage": {"has_gaps": True, "overall_coverage": 50.0},
        })
        assert retry.until(ctx) is False, (
            "until should return False on first attempt (no _prev_coverage)"
        )

    def test_until_exits_when_no_gaps(self):
        """coverage-retry should exit when no gaps remain (original condition)."""
        mod = _load_workflow_module("develop")
        wf = mod.WORKFLOW
        retry = _find_block(wf.blocks, "coverage-retry", "retry")

        WorkflowContext = _types_ns["WorkflowContext"]
        ctx = WorkflowContext(variables={
            "coverage": {"has_gaps": False, "overall_coverage": 100.0},
        })
        assert retry.until(ctx) is True, (
            "until should return True when has_gaps is False"
        )


class TestAcceptanceCheckScope:
    """Verify acceptance-check audits all units."""

    def test_acceptance_prompt_uses_units_not_unit(self):
        """03g-acceptance-check.md must use {{variables.units}}, not {{variables.unit}}."""
        prompt_path = STATIC_WORKFLOWS / "develop" / "prompts" / "03g-acceptance-check.md"
        assert prompt_path.exists()
        content = prompt_path.read_text()

        assert "{{variables.unit}}" not in content, (
            "Prompt still uses {{variables.unit}} which only holds the last loop iteration. "
            "Should use {{variables.units}} for all units."
        )
        assert "{{variables.units}}" in content, (
            "Prompt must use {{variables.units}} to audit all units"
        )
