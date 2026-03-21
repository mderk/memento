"""Tests for create-protocol plan.json edit flow (protocol 0004).

Verifies:
- create-protocol workflow saves plan.json after generation
- create-protocol workflow detects existing plan.json
- create-protocol workflow has edit flow (load → ask user → LLM edit → save)
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
        for attr in ("blocks", "template", "default"):
            nested = getattr(block, attr, None)
            if nested and isinstance(nested, list):
                found = _find_block(nested, name, block_type)
                if found:
                    return found
        # Check ConditionalBlock branches
        branches = getattr(block, "branches", None)
        if branches:
            for branch in branches:
                found = _find_block(branch.blocks, name, block_type)
                if found:
                    return found
    return None


class TestCreateProtocolPlanJson:
    """Verify create-protocol saves and reuses plan.json."""

    def test_save_plan_json_step_exists(self):
        """Workflow must have a step that saves plan.json to protocol dir."""
        mod = _load_workflow_module("create-protocol")
        wf = mod.WORKFLOW
        save_step = _find_block(wf.blocks, "save-plan-json")
        assert save_step is not None, (
            "ShellStep 'save-plan-json' not found. Needed to persist plan JSON "
            "for subsequent editing."
        )

    def test_has_plan_exists_check(self):
        """Workflow must check if plan.json already exists."""
        mod = _load_workflow_module("create-protocol")
        wf = mod.WORKFLOW
        check = _find_block(wf.blocks, "check-plan-exists")
        assert check is not None, (
            "Step 'check-plan-exists' not found. Needed to detect existing plan.json "
            "for edit flow."
        )

    def test_has_edit_prompt(self):
        """Workflow must have an edit prompt for modifying existing plans."""
        mod = _load_workflow_module("create-protocol")
        wf = mod.WORKFLOW
        edit_step = _find_block(wf.blocks, "edit-plan")
        assert edit_step is not None, (
            "LLMStep 'edit-plan' not found. Needed for conversational plan editing."
        )

    def test_has_ask_user_for_changes(self):
        """Workflow must ask user what to change when plan exists."""
        mod = _load_workflow_module("create-protocol")
        wf = mod.WORKFLOW
        ask_step = _find_block(wf.blocks, "ask-edit-instructions")
        assert ask_step is not None, (
            "PromptStep 'ask-edit-instructions' not found. Needed to get user's "
            "edit instructions."
        )
