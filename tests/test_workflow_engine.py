"""Tests for workflow engine types, condition evaluation, template substitution, and dry-run execution."""

import asyncio
import json
import re
from pathlib import Path

import pytest
from pydantic import BaseModel

# Load engine and types modules directly (avoid package import issues)
SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "workflow-engine"
    / "scripts"
)

WORKFLOWS_DIR = (
    Path(__file__).resolve().parent.parent
    / "static"
    / "workflows"
)
# Plugin-only workflows (not deployed to user projects, in skills/)
PLUGIN_SKILLS_DIR = (
    Path(__file__).resolve().parent.parent
    / "skills"
)


def _strip_relative_imports(code: str) -> str:
    """Remove all 'from .xxx import (...)' and 'from .xxx import yyy' blocks."""
    # Multi-line: from .foo import (\n  ...\n)  or from ..foo import (\n ...\n)
    code = re.sub(r"from \.+\w+ import \(.*?\)", "", code, flags=re.DOTALL)
    # Single-line: from .foo import bar  or from ..foo import bar
    code = re.sub(r"from \.+\w+ import .+", "", code)
    return code


# Load types
_types_code = (SCRIPTS_DIR / "types.py").read_text()
_types_ns: dict = {"__name__": "types", "__annotations__": {}}
exec(compile(_types_code, str(SCRIPTS_DIR / "types.py"), "exec"), _types_ns)

LLMStep = _types_ns["LLMStep"]
GroupBlock = _types_ns["GroupBlock"]
ParallelEachBlock = _types_ns["ParallelEachBlock"]
LoopBlock = _types_ns["LoopBlock"]
RetryBlock = _types_ns["RetryBlock"]
SubWorkflow = _types_ns["SubWorkflow"]
ShellStep = _types_ns["ShellStep"]
PromptStep = _types_ns["PromptStep"]
ConditionalBlock = _types_ns["ConditionalBlock"]
Branch = _types_ns["Branch"]
WorkflowDef = _types_ns["WorkflowDef"]
WorkflowContext = _types_ns["WorkflowContext"]
StepResult = _types_ns["StepResult"]

# Load engine (with relative imports stripped, types injected)
_engine_code = _strip_relative_imports((SCRIPTS_DIR / "engine.py").read_text())
_engine_ns: dict = {
    "__name__": "engine",
    "__annotations__": {},
    # Inject types into engine namespace
    "LLMStep": LLMStep,
    "GroupBlock": GroupBlock,
    "ParallelEachBlock": ParallelEachBlock,
    "LoopBlock": LoopBlock,
    "RetryBlock": RetryBlock,
    "SubWorkflow": SubWorkflow,
    "ShellStep": ShellStep,
    "PromptStep": PromptStep,
    "ConditionalBlock": ConditionalBlock,
    "Branch": Branch,
    "WorkflowDef": WorkflowDef,
    "WorkflowContext": WorkflowContext,
    "StepResult": StepResult,
    "Block": _types_ns["Block"],
}
exec(compile(_engine_code, str(SCRIPTS_DIR / "engine.py"), "exec"), _engine_ns)

evaluate_condition = _engine_ns["evaluate_condition"]
_substitute = _engine_ns["_substitute"]
load_prompt = _engine_ns["load_prompt"]
execute_shell = _engine_ns["execute_shell"]
execute_llm_step = _engine_ns["execute_llm_step"]
execute_loop = _engine_ns["execute_loop"]
execute_retry = _engine_ns["execute_retry"]
execute_block = _engine_ns["execute_block"]
execute_workflow = _engine_ns["execute_workflow"]
execute_parallel_each = _engine_ns["execute_parallel_each"]
execute_group = _engine_ns["execute_group"]
execute_sub_workflow = _engine_ns["execute_sub_workflow"]
execute_prompt_step = _engine_ns["execute_prompt_step"]
execute_conditional = _engine_ns["execute_conditional"]
StopForInput = _engine_ns["StopForInput"]
StdinIOHandler = _engine_ns["StdinIOHandler"]
PresetIOHandler = _engine_ns["PresetIOHandler"]
StopIOHandler = _engine_ns["StopIOHandler"]
_emit = _engine_ns["_emit"]

# Load loader (with relative imports stripped, types injected)
_loader_code = _strip_relative_imports((SCRIPTS_DIR / "loader.py").read_text())
_loader_ns: dict = {
    "__name__": "loader",
    "__annotations__": {},
    "__builtins__": __builtins__,
    "WorkflowDef": WorkflowDef,
    "LLMStep": LLMStep,
    "GroupBlock": GroupBlock,
    "ParallelEachBlock": ParallelEachBlock,
    "LoopBlock": LoopBlock,
    "RetryBlock": RetryBlock,
    "SubWorkflow": SubWorkflow,
    "ShellStep": ShellStep,
    "PromptStep": PromptStep,
    "ConditionalBlock": ConditionalBlock,
    "Branch": Branch,
    "WorkflowContext": WorkflowContext,
    "Path": Path,
}
exec(compile(_loader_code, str(SCRIPTS_DIR / "loader.py"), "exec"), _loader_ns)

load_workflow = _loader_ns["load_workflow"]
discover_workflows = _loader_ns["discover_workflows"]


def _load_workflow_file(workflow_name: str) -> dict:
    """Load a workflow definition from workflows directory."""
    workflow_dir = PLUGIN_SKILLS_DIR / workflow_name
    if not workflow_dir.exists():
        workflow_dir = WORKFLOWS_DIR / workflow_name
    code = (workflow_dir / "workflow.py").read_text()
    ns = dict(_types_ns)
    ns["__name__"] = workflow_name
    exec(compile(code, str(workflow_dir / "workflow.py"), "exec"), ns)
    return ns


# ============ WorkflowContext ============


class TestWorkflowContext:
    def test_get_var_variables(self):
        ctx = WorkflowContext(variables={"mode": "protocol", "task": "add login"})
        assert ctx.get_var("variables.mode") == "protocol"
        assert ctx.get_var("variables.task") == "add login"

    def test_get_var_nested(self):
        ctx = WorkflowContext(variables={"config": {"debug": True, "level": 3}})
        assert ctx.get_var("variables.config.debug") is True
        assert ctx.get_var("variables.config.level") == 3

    def test_get_var_results(self):
        ctx = WorkflowContext()
        ctx.results["classify"] = StepResult(
            name="classify", status="success",
            structured_output={"scope": "backend", "fast_track": False},
        )
        assert ctx.get_var("results.classify.structured_output.scope") == "backend"
        assert ctx.get_var("results.classify.status") == "success"

    def test_get_var_cwd(self):
        ctx = WorkflowContext(cwd="/my/project")
        assert ctx.get_var("cwd") == "/my/project"

    def test_get_var_missing(self):
        ctx = WorkflowContext()
        assert ctx.get_var("results.nonexistent") is None
        assert ctx.get_var("variables.missing") is None
        assert ctx.get_var("unknown.path") is None

    def test_elapsed(self):
        ctx = WorkflowContext()
        assert ctx.elapsed() >= 0

    def test_result_field(self):
        ctx = WorkflowContext()
        ctx.results["verify-green"] = StepResult(
            name="verify-green",
            structured_output={"status": "green", "failures": []},
        )
        assert ctx.result_field("verify-green", "status") == "green"
        assert ctx.result_field("verify-green", "failures") == []
        assert ctx.result_field("verify-green", "missing") is None
        assert ctx.result_field("nonexistent", "status") is None

    def test_result_field_no_structured_output(self):
        ctx = WorkflowContext()
        ctx.results["step"] = StepResult(name="step")
        assert ctx.result_field("step", "anything") is None


# ============ Template Substitution ============


class TestSubstitute:
    def test_variable_substitution(self):
        ctx = WorkflowContext(variables={"task": "add login", "mode": "protocol"})
        result = _substitute("Task: {{variables.task}}, Mode: {{variables.mode}}", ctx)
        assert result == "Task: add login, Mode: protocol"

    def test_result_substitution(self):
        ctx = WorkflowContext()
        ctx.results["classify"] = StepResult(name="classify", output="backend bug")
        result = _substitute("Classification: {{results.classify.output}}", ctx)
        assert result == "Classification: backend bug"

    def test_unresolved_left_as_is(self):
        ctx = WorkflowContext()
        result = _substitute("Value: {{variables.missing}}", ctx)
        assert result == "Value: {{variables.missing}}"

    def test_dict_substitution(self):
        ctx = WorkflowContext(variables={"data": {"key": "value"}})
        result = _substitute("Data: {{variables.data}}", ctx)
        parsed = json.loads(result.replace("Data: ", ""))
        assert parsed == {"key": "value"}

    def test_no_templates(self):
        ctx = WorkflowContext()
        assert _substitute("plain text", ctx) == "plain text"

    def test_cwd_substitution(self):
        ctx = WorkflowContext(cwd="/my/project")
        result = _substitute("path: {{cwd}}/.memory_bank", ctx)
        assert result == "path: /my/project/.memory_bank"


# ============ Condition Evaluation ============


class TestEvaluateCondition:
    def test_none_is_true(self):
        ctx = WorkflowContext()
        assert evaluate_condition(None, ctx) is True

    def test_callable_true(self):
        ctx = WorkflowContext(variables={"fast_track": True})
        assert evaluate_condition(lambda ctx: ctx.variables.get("fast_track"), ctx) is True

    def test_callable_false(self):
        ctx = WorkflowContext(variables={"fast_track": False})
        assert evaluate_condition(lambda ctx: ctx.variables.get("fast_track"), ctx) is False

    def test_not_expression(self):
        ctx = WorkflowContext(variables={"fast_track": False})
        assert evaluate_condition(lambda ctx: not ctx.variables.get("fast_track"), ctx) is True

    def test_string_comparison(self):
        ctx = WorkflowContext(variables={"mode": "protocol"})
        assert evaluate_condition(lambda ctx: ctx.variables.get("mode") == "protocol", ctx) is True
        assert evaluate_condition(lambda ctx: ctx.variables.get("mode") != "protocol", ctx) is False

    def test_result_field_check(self):
        ctx = WorkflowContext()
        ctx.results["verify-green"] = StepResult(
            name="verify-green",
            structured_output={"status": "green"},
        )
        assert evaluate_condition(
            lambda ctx: ctx.result_field("verify-green", "status") == "green", ctx
        ) is True

    def test_result_field_mismatch(self):
        ctx = WorkflowContext()
        ctx.results["verify-green"] = StepResult(
            name="verify-green",
            structured_output={"status": "red"},
        )
        assert evaluate_condition(
            lambda ctx: ctx.result_field("verify-green", "status") == "green", ctx
        ) is False

    def test_negated_result_field(self):
        ctx = WorkflowContext()
        ctx.results["synthesize"] = StepResult(
            name="synthesize",
            structured_output={"has_blockers": False},
        )
        assert evaluate_condition(
            lambda ctx: not ctx.result_field("synthesize", "has_blockers"), ctx
        ) is True

    def test_result_field_truthy(self):
        ctx = WorkflowContext()
        ctx.results["synthesize"] = StepResult(
            name="synthesize",
            structured_output={"has_blockers": True},
        )
        assert evaluate_condition(
            lambda ctx: not ctx.result_field("synthesize", "has_blockers"), ctx
        ) is False

    def test_dotted_result_key(self):
        """Result keys with dots work directly via result_field."""
        ctx = WorkflowContext()
        ctx.results["re-review.synthesize"] = StepResult(
            name="re-review.synthesize",
            structured_output={"has_blockers": False},
        )
        assert evaluate_condition(
            lambda ctx: not ctx.result_field("re-review.synthesize", "has_blockers"), ctx
        ) is True


# ============ Load Prompt ============


class TestLoadPrompt:
    def test_basic_load(self, tmp_path):
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "test.md").write_text("Hello {{variables.name}}!")
        ctx = WorkflowContext(
            variables={"name": "World"},
            prompt_dir=str(prompt_dir),
        )
        result = load_prompt("test.md", ctx)
        assert result == "Hello World!"

    def test_load_with_results(self, tmp_path):
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "test.md").write_text("Previous: {{results.step1.output}}")
        ctx = WorkflowContext(prompt_dir=str(prompt_dir))
        ctx.results["step1"] = StepResult(name="step1", output="done")
        result = load_prompt("test.md", ctx)
        assert result == "Previous: done"


# ============ ShellStep Execution ============


class TestExecuteShell:
    def test_basic_command(self):
        ctx = WorkflowContext(cwd="/tmp")
        step = ShellStep(name="echo-test", command="echo hello")
        result = execute_shell(step, ctx)
        assert result.status == "success"
        assert "hello" in result.output

    def test_failing_command(self):
        ctx = WorkflowContext(cwd="/tmp")
        step = ShellStep(name="fail-test", command="exit 1")
        result = execute_shell(step, ctx)
        assert result.status == "failure"

    def test_condition_skip(self):
        ctx = WorkflowContext(variables={"skip": True})
        step = ShellStep(
            name="skipped", command="echo should-not-run",
            condition=lambda ctx: not ctx.variables.get("skip"),
        )
        result = execute_shell(step, ctx)
        assert result.status == "skipped"

    def test_dry_run(self):
        ctx = WorkflowContext(dry_run=True)
        step = ShellStep(name="dry", command="rm -rf /")
        result = execute_shell(step, ctx)
        assert result.status == "dry_run"
        assert "[dry-run]" in result.output

    def test_variable_substitution(self):
        ctx = WorkflowContext(variables={"name": "world"}, cwd="/tmp")
        step = ShellStep(name="sub", command="echo {{variables.name}}")
        result = execute_shell(step, ctx)
        assert result.status == "success"
        assert "world" in result.output

    def test_result_stored_in_context(self):
        ctx = WorkflowContext(cwd="/tmp")
        step = ShellStep(name="stored", command="echo stored-value")
        execute_shell(step, ctx)
        assert "stored" in ctx.results
        assert ctx.results["stored"].status == "success"


# ============ LLMStep Dry Run ============


class TestLLMStepDryRun:
    def test_dry_run_skips_sdk(self):
        ctx = WorkflowContext(
            dry_run=True,
            prompt_dir="/tmp",
            variables={"task": "test"},
        )
        step = LLMStep(
            name="test-step",
            prompt="nonexistent.md",
            tools=["Read"],
        )
        result = asyncio.run(execute_llm_step(step, ctx))
        assert result.status == "dry_run"
        assert "[dry-run]" in result.output

    def test_condition_skip(self):
        ctx = WorkflowContext(dry_run=True, variables={"fast_track": True})
        step = LLMStep(
            name="explore",
            prompt="explore.md",
            tools=["Read"],
            condition=lambda ctx: not ctx.variables.get("fast_track"),
        )
        result = asyncio.run(execute_llm_step(step, ctx))
        assert result.status == "skipped"


# ============ LoopBlock Dry Run ============


class TestLoopBlockDryRun:
    def test_loop_iterates_items(self):
        ctx = WorkflowContext(dry_run=True, prompt_dir="/tmp")
        ctx.results["plan"] = StepResult(
            name="plan",
            structured_output={"tasks": [
                {"id": "t1", "description": "Task 1"},
                {"id": "t2", "description": "Task 2"},
            ]},
        )
        loop = LoopBlock(
            name="implement",
            loop_over="results.plan.structured_output.tasks",
            loop_var="unit",
            blocks=[
                ShellStep(name="echo", command="echo {{variables.unit}}"),
            ],
        )
        results = asyncio.run(execute_loop(loop, ctx))
        assert len(results) == 2
        assert all(r.status == "dry_run" for r in results)

    def test_loop_not_a_list(self):
        ctx = WorkflowContext(dry_run=True)
        loop = LoopBlock(
            name="bad-loop",
            loop_over="variables.missing",
            loop_var="item",
            blocks=[],
        )
        results = asyncio.run(execute_loop(loop, ctx))
        assert len(results) == 1
        assert results[0].status == "failure"

    def test_loop_condition_skip(self):
        ctx = WorkflowContext(variables={"skip_loop": True})
        loop = LoopBlock(
            name="skipped-loop",
            loop_over="variables.items",
            loop_var="item",
            blocks=[],
            condition=lambda ctx: not ctx.variables.get("skip_loop"),
        )
        results = asyncio.run(execute_loop(loop, ctx))
        assert len(results) == 1
        assert results[0].status == "skipped"

    def test_loop_restores_loop_variables(self):
        ctx = WorkflowContext(dry_run=True)
        ctx.variables = {"items": ["x", "y"], "item": "orig", "item_index": 99}
        loop = LoopBlock(
            name="loop",
            loop_over="variables.items",
            loop_var="item",
            blocks=[ShellStep(name="noop", command="echo ok")],
        )
        asyncio.run(execute_loop(loop, ctx))
        assert ctx.variables["item"] == "orig"
        assert ctx.variables["item_index"] == 99

    def test_loop_cleans_up_loop_variables_when_absent(self):
        ctx = WorkflowContext(dry_run=True)
        ctx.variables = {"items": ["x"]}
        loop = LoopBlock(
            name="loop",
            loop_over="variables.items",
            loop_var="item",
            blocks=[ShellStep(name="noop", command="echo ok")],
        )
        asyncio.run(execute_loop(loop, ctx))
        assert "item" not in ctx.variables
        assert "item_index" not in ctx.variables


# ============ RetryBlock Dry Run ============


class TestRetryBlockDryRun:
    def test_retry_stops_on_condition(self):
        ctx = WorkflowContext(dry_run=True, cwd="/tmp")
        retry = RetryBlock(
            name="green-loop",
            until=lambda ctx: ctx.result_field("verify-green", "status") == "green",
            max_attempts=3,
            blocks=[
                ShellStep(name="check", command="echo checking"),
            ],
        )
        # Simulate green after first attempt
        ctx.results["verify-green"] = StepResult(
            name="verify-green",
            structured_output={"status": "green"},
        )
        results = asyncio.run(execute_retry(retry, ctx))
        # Should execute blocks once then stop (condition already true)
        assert len(results) == 1

    def test_retry_exhausts_attempts(self):
        ctx = WorkflowContext(dry_run=True, cwd="/tmp")
        retry = RetryBlock(
            name="retry-loop",
            until=lambda ctx: ctx.result_field("verify-green", "status") == "green",
            max_attempts=2,
            blocks=[
                ShellStep(name="try", command="echo trying"),
            ],
        )
        results = asyncio.run(execute_retry(retry, ctx))
        # 'green' never satisfied, runs max_attempts times
        assert len(results) == 2

    def test_retry_restores_attempt_variable(self):
        ctx = WorkflowContext(dry_run=True)
        ctx.variables = {"attempt": 42}
        retry = RetryBlock(
            name="r",
            until=lambda _ctx: True,
            max_attempts=3,
            blocks=[ShellStep(name="noop", command="echo ok")],
        )
        asyncio.run(execute_retry(retry, ctx))
        assert ctx.variables["attempt"] == 42

    def test_retry_cleans_up_attempt_variable_when_absent(self):
        ctx = WorkflowContext(dry_run=True)
        retry = RetryBlock(
            name="r",
            until=lambda _ctx: True,
            max_attempts=3,
            blocks=[ShellStep(name="noop", command="echo ok")],
        )
        asyncio.run(execute_retry(retry, ctx))
        assert "attempt" not in ctx.variables


# ============ ParallelEachBlock Dry Run ============


class TestParallelEachBlockDryRun:
    def test_parallel_items(self):
        ctx = WorkflowContext(dry_run=True, prompt_dir="/tmp")
        ctx.results["scope"] = StepResult(
            name="scope",
            structured_output={"competencies": ["architecture", "security", "simplicity"]},
        )
        parallel = ParallelEachBlock(
            name="reviews",
            parallel_for="results.scope.structured_output.competencies",
            template=[
                LLMStep(
                    name="review",
                    prompt="review.md",
                    tools=["Read"],
                )
            ],
        )
        results = asyncio.run(execute_parallel_each(parallel, ctx))
        assert len(results) == 3
        assert all(r.status == "dry_run" for r in results)
        # Deterministic scoped identity: each parallel instance has a unique exec_key.
        assert len({r.exec_key for r in results}) == 3
        # Convenience view is last-by-index (i=2).
        assert ctx.results["review"].exec_key.endswith("par:reviews[i=2]/review")

    def test_parallel_not_a_list(self):
        ctx = WorkflowContext(dry_run=True)
        parallel = ParallelEachBlock(
            name="bad-parallel",
            parallel_for="variables.missing",
            template=[LLMStep(name="t", prompt="t.md", tools=[])],
        )
        results = asyncio.run(execute_parallel_each(parallel, ctx))
        assert len(results) == 1
        assert results[0].status == "failure"

    def test_parallel_does_not_mutate_parent_nested_variables(self):
        """Parallel child contexts must not share nested variable objects."""
        ctx = WorkflowContext(dry_run=True)
        ctx.variables = {
            "items": ["a", "b", "c"],
            "nested": {"seen": []},
        }

        def mutate_nested(child_ctx):
            # Runs during execute_llm_step's condition evaluation in each branch.
            child_ctx.variables["nested"]["seen"].append(child_ctx.variables["item"])
            return True

        parallel = ParallelEachBlock(
            name="p",
            parallel_for="variables.items",
            template=[
                LLMStep(
                    name="t",
                    prompt="t.md",
                    tools=[],
                    condition=mutate_nested,
                )
            ],
        )
        asyncio.run(execute_parallel_each(parallel, ctx))
        # If shallow-copied, this would contain ["a", "b", "c"].
        assert ctx.variables["nested"]["seen"] == []


# ============ SubWorkflow Dry Run ============


class TestSubWorkflowDryRun:
    def test_sub_workflow_calls_child(self):
        child_wf = WorkflowDef(
            name="child",
            description="test child",
            blocks=[
                ShellStep(name="child-step", command="echo child"),
            ],
        )
        registry = {"child": child_wf}
        ctx = WorkflowContext(dry_run=True, cwd="/tmp")
        sub = SubWorkflow(
            name="run-child",
            workflow="child",
        )
        results = asyncio.run(execute_sub_workflow(sub, ctx, registry=registry))
        assert len(results) == 1
        assert results[0].status == "dry_run"

    def test_sub_workflow_unknown(self):
        ctx = WorkflowContext(dry_run=True)
        sub = SubWorkflow(name="bad", workflow="nonexistent")
        results = asyncio.run(execute_sub_workflow(sub, ctx, registry={}))
        assert len(results) == 1
        assert results[0].status == "failure"

    def test_sub_workflow_injects_variables(self):
        child_wf = WorkflowDef(
            name="child",
            description="test child",
            blocks=[
                ShellStep(name="check-var", command="echo {{variables.injected}}"),
            ],
        )
        registry = {"child": child_wf}
        ctx = WorkflowContext(dry_run=True, cwd="/tmp")
        sub = SubWorkflow(
            name="inject",
            workflow="child",
            inject={"injected": "hello"},
        )
        results = asyncio.run(execute_sub_workflow(sub, ctx, registry=registry))
        assert len(results) == 1

    def test_sub_workflow_condition_skip(self):
        ctx = WorkflowContext(variables={"mode": "protocol"})
        sub = SubWorkflow(
            name="skipped",
            workflow="anything",
            condition=lambda ctx: ctx.variables.get("mode") != "protocol",
        )
        results = asyncio.run(execute_sub_workflow(sub, ctx, registry={}))
        assert len(results) == 1
        assert results[0].status == "skipped"

    def test_sub_workflow_uses_child_prompt_dir(self):
        """Sub-workflow should use its own prompt_dir, not the parent's."""
        child_wf = WorkflowDef(
            name="child",
            description="test child",
            prompt_dir="/child/prompts",
            blocks=[
                ShellStep(name="child-step", command="echo child"),
            ],
        )
        registry = {"child": child_wf}
        ctx = WorkflowContext(dry_run=True, cwd="/tmp", prompt_dir="/parent/prompts")
        sub = SubWorkflow(name="run-child", workflow="child")
        asyncio.run(execute_sub_workflow(sub, ctx, registry=registry))
        # Parent prompt_dir should not be overwritten
        assert ctx.prompt_dir == "/parent/prompts"


# ============ Full Workflow Dry Run ============


class TestExecuteWorkflow:
    def test_simple_workflow(self):
        wf = WorkflowDef(
            name="test",
            description="test workflow",
            blocks=[
                ShellStep(name="step1", command="echo one"),
                ShellStep(name="step2", command="echo two"),
            ],
        )
        ctx = WorkflowContext(dry_run=True, cwd="/tmp")
        results = asyncio.run(execute_workflow(wf, ctx))
        assert len(results) == 2
        assert all(r.status == "dry_run" for r in results)

    def test_mixed_block_types(self):
        wf = WorkflowDef(
            name="mixed",
            description="mixed blocks",
            blocks=[
                ShellStep(name="shell", command="echo hello"),
                LLMStep(name="step", prompt="test.md", tools=["Read"]),
            ],
        )
        ctx = WorkflowContext(dry_run=True, cwd="/tmp", prompt_dir="/tmp")
        results = asyncio.run(execute_workflow(wf, ctx))
        assert len(results) == 2

    def test_workflow_sets_prompt_dir(self):
        """execute_workflow should set ctx.prompt_dir from workflow.prompt_dir."""
        wf = WorkflowDef(
            name="test",
            description="test",
            prompt_dir="/my/prompts",
            blocks=[
                ShellStep(name="step1", command="echo hello"),
            ],
        )
        ctx = WorkflowContext(dry_run=True, cwd="/tmp")
        asyncio.run(execute_workflow(wf, ctx))
        assert ctx.prompt_dir == "/my/prompts"


# ============ Loader ============


class TestLoader:
    def test_load_workflow_from_dir(self, tmp_path):
        """load_workflow loads a workflow.py and auto-sets prompt_dir."""
        wf_dir = tmp_path / "my-workflow"
        wf_dir.mkdir()
        (wf_dir / "prompts").mkdir()
        (wf_dir / "workflow.py").write_text(
            'WORKFLOW = WorkflowDef(name="my-workflow", description="test")\n'
        )
        wf = load_workflow(wf_dir)
        assert wf.name == "my-workflow"
        assert wf.prompt_dir == str(wf_dir / "prompts")

    def test_load_workflow_preserves_explicit_prompt_dir(self, tmp_path):
        """If workflow.py sets prompt_dir, loader should not override it."""
        wf_dir = tmp_path / "my-workflow"
        wf_dir.mkdir()
        (wf_dir / "workflow.py").write_text(
            'WORKFLOW = WorkflowDef(name="my-wf", description="test", prompt_dir="/custom")\n'
        )
        wf = load_workflow(wf_dir)
        assert wf.prompt_dir == "/custom"

    def test_discover_workflows(self, tmp_path):
        """discover_workflows finds workflow packages in search paths."""
        wf1 = tmp_path / "wf1"
        wf1.mkdir()
        (wf1 / "workflow.py").write_text(
            'WORKFLOW = WorkflowDef(name="first", description="test1")\n'
        )
        wf2 = tmp_path / "wf2"
        wf2.mkdir()
        (wf2 / "workflow.py").write_text(
            'WORKFLOW = WorkflowDef(name="second", description="test2")\n'
        )
        # non-workflow dir (no workflow.py)
        (tmp_path / "not-a-workflow").mkdir()

        registry = discover_workflows(tmp_path)
        assert len(registry) == 2
        assert "first" in registry
        assert "second" in registry

    def test_discover_workflows_missing_dir(self, tmp_path):
        """discover_workflows skips nonexistent paths."""
        registry = discover_workflows(tmp_path / "nonexistent")
        assert registry == {}

    def test_discover_workflows_multiple_paths(self, tmp_path):
        """discover_workflows scans multiple search paths."""
        dir1 = tmp_path / "dir1"
        dir1.mkdir()
        (dir1 / "a").mkdir()
        (dir1 / "a" / "workflow.py").write_text(
            'WORKFLOW = WorkflowDef(name="a", description="from dir1")\n'
        )
        dir2 = tmp_path / "dir2"
        dir2.mkdir()
        (dir2 / "b").mkdir()
        (dir2 / "b" / "workflow.py").write_text(
            'WORKFLOW = WorkflowDef(name="b", description="from dir2")\n'
        )
        registry = discover_workflows(dir1, dir2)
        assert "a" in registry
        assert "b" in registry

    def test_load_real_develop_workflow(self):
        """Load the actual develop workflow from static/workflows/."""
        wf = load_workflow(WORKFLOWS_DIR / "develop")
        assert wf.name == "development"
        assert len(wf.blocks) > 0
        assert wf.prompt_dir == str(WORKFLOWS_DIR / "develop" / "prompts")

    def test_load_real_code_review_workflow(self):
        """Load the actual code-review workflow from static/workflows/."""
        wf = load_workflow(WORKFLOWS_DIR / "code-review")
        assert wf.name == "code-review"

    def test_load_real_testing_workflow(self):
        """Load the actual testing workflow from static/workflows/."""
        wf = load_workflow(WORKFLOWS_DIR / "testing")
        assert wf.name == "testing"

    def test_load_real_process_protocol_workflow(self):
        """Load the actual process-protocol workflow from static/workflows/."""
        wf = load_workflow(WORKFLOWS_DIR / "process-protocol")
        assert wf.name == "process-protocol"

    def test_load_real_create_environment_workflow(self):
        """Load the actual create-environment workflow from skills/ (plugin-only)."""
        wf = load_workflow(PLUGIN_SKILLS_DIR / "create-environment")
        assert wf.name == "create-environment"

    def test_discover_real_workflows(self):
        """discover_workflows finds 4 deployed workflows from static/workflows/."""
        registry = discover_workflows(WORKFLOWS_DIR)
        assert len(registry) == 4
        assert "development" in registry
        assert "code-review" in registry
        assert "testing" in registry
        assert "process-protocol" in registry

    def test_discover_direct_workflow_dir(self):
        """discover_workflows loads workflow.py directly when path contains it."""
        registry = discover_workflows(PLUGIN_SKILLS_DIR / "create-environment")
        assert len(registry) == 1
        assert "create-environment" in registry

    def test_discover_with_plugin_skills(self):
        """discover_workflows finds all 6 workflows when both dirs are searched."""
        registry = discover_workflows(
            WORKFLOWS_DIR,
            PLUGIN_SKILLS_DIR / "create-environment",
            PLUGIN_SKILLS_DIR / "update-environment",
        )
        assert len(registry) == 6
        assert "create-environment" in registry
        assert "update-environment" in registry


# ============ Workflow Definitions ============


class TestWorkflowDefinitions:
    def test_development_loads(self):
        ns = _load_workflow_file("develop")
        assert "WORKFLOW" in ns
        assert ns["WORKFLOW"].name == "development"
        assert len(ns["WORKFLOW"].blocks) > 0

    def test_code_review_loads(self):
        ns = _load_workflow_file("code-review")
        assert "WORKFLOW" in ns
        assert ns["WORKFLOW"].name == "code-review"

    def test_testing_loads(self):
        ns = _load_workflow_file("testing")
        assert "WORKFLOW" in ns
        assert ns["WORKFLOW"].name == "testing"

    def test_process_protocol_loads(self):
        ns = _load_workflow_file("process-protocol")
        assert "WORKFLOW" in ns
        assert ns["WORKFLOW"].name == "process-protocol"

    def test_create_environment_loads(self):
        ns = _load_workflow_file("create-environment")
        assert "WORKFLOW" in ns
        assert ns["WORKFLOW"].name == "create-environment"

    def test_development_has_expected_phases(self):
        ns = _load_workflow_file("develop")
        block_names = [b.name for b in ns["WORKFLOW"].blocks]
        assert "understand" in block_names
        assert "plan" in block_names
        assert "implement" in block_names
        assert "review" in block_names
        assert "complete" in block_names

    def test_code_review_has_parallel_block(self):
        ns = _load_workflow_file("code-review")
        cr = ns["WORKFLOW"]
        parallel_blocks = [b for b in cr.blocks if type(b).__name__ == "ParallelEachBlock"]
        assert len(parallel_blocks) == 1
        assert parallel_blocks[0].name == "reviews"

    def test_test_workflow_loads(self):
        ns = _load_workflow_file("test-workflow")
        assert "WORKFLOW" in ns
        assert ns["WORKFLOW"].name == "test-workflow"

    def test_test_workflow_has_all_block_types(self):
        """test-workflow exercises all 9 engine block types."""
        ns = _load_workflow_file("test-workflow")
        wf = ns["WORKFLOW"]

        def _collect_types(blocks, depth=0):
            types = set()
            for b in blocks:
                types.add(type(b).__name__)
                if hasattr(b, "blocks"):
                    types |= _collect_types(b.blocks, depth + 1)
                if hasattr(b, "branches"):
                    for branch in b.branches:
                        types |= _collect_types(branch.blocks, depth + 1)
                if hasattr(b, "default") and isinstance(b.default, list):
                    types |= _collect_types(b.default, depth + 1)
                if hasattr(b, "template"):
                    tmpl = getattr(b, "template")
                    if isinstance(tmpl, list):
                        types |= _collect_types(tmpl, depth + 1)
                    else:
                        types.add(type(tmpl).__name__)
            return types

        all_types = _collect_types(wf.blocks)
        expected = {
            "ShellStep", "PromptStep", "ConditionalBlock", "LoopBlock",
            "RetryBlock", "SubWorkflow", "LLMStep", "GroupBlock", "ParallelEachBlock",
        }
        assert expected == all_types, f"Missing: {expected - all_types}, Extra: {all_types - expected}"

    def test_test_workflow_has_18_top_level_blocks(self):
        ns = _load_workflow_file("test-workflow")
        wf = ns["WORKFLOW"]
        block_names = [b.name for b in wf.blocks]
        assert "detect" in block_names
        assert "retry-flaky" in block_names
        assert "call-helper" in block_names
        assert "loop-retry-items" in block_names
        assert "llm-classify" in block_names
        assert "llm-session" in block_names
        assert "parallel-gate" in block_names
        assert "llm-ask-single" in block_names
        assert "llm-ask-group" in block_names
        assert "parallel-ask-gate" in block_names
        assert "cleanup" in block_names

    def test_test_workflow_sub_workflow_discovered(self):
        """discover_workflows finds test-helper sub-workflow."""
        sub_dir = PLUGIN_SKILLS_DIR / "test-workflow" / "sub-workflows"
        registry = discover_workflows(sub_dir)
        assert "test-helper" in registry
        assert len(registry["test-helper"].blocks) == 2


# ============ Output Schemas (Pydantic models in workflow files) ============


class TestOutputSchemas:
    def test_develop_schemas(self):
        ns = _load_workflow_file("develop")
        # ClassifyOutput
        schema = ns["ClassifyOutput"].model_json_schema()
        assert "scope" in schema["properties"]
        assert "fast_track" in schema["properties"]
        # PlanOutput
        schema = ns["PlanOutput"].model_json_schema()
        assert "tasks" in schema["properties"]
        # TestStatus
        obj = ns["TestStatus"](status="green")
        assert obj.failures == []

    def test_code_review_schemas(self):
        ns = _load_workflow_file("code-review")
        schema = ns["ReviewFindings"].model_json_schema()
        assert "findings" in schema["properties"]
        assert "has_blockers" in schema["properties"]
        obj = ns["ReviewFindings"](findings=[], has_blockers=False, verdict="APPROVE")
        assert obj.has_blockers is False

    def test_testing_schemas(self):
        ns = _load_workflow_file("testing")
        schema = ns["TestResults"].model_json_schema()
        assert "passed" in schema["properties"]
        assert "failed" in schema["properties"]
        obj = ns["TestResults"](passed=10, failed=0, errors=0)
        assert obj.coverage_pct is None

    def test_test_workflow_summary_schema(self):
        ns = _load_workflow_file("test-workflow")
        schema = ns["SummaryOutput"].model_json_schema()
        assert "total_items" in schema["properties"]
        assert "status" in schema["properties"]
        assert "notes" in schema["properties"]
        obj = ns["SummaryOutput"](total_items=3, status="complete", notes="test")
        assert obj.total_items == 3

    def test_output_schema_references_model_class(self):
        """LLMStep.output_schema holds the model class, not a string path."""
        ns = _load_workflow_file("develop")
        classify_step = ns["WORKFLOW"].blocks[0].blocks[0]
        assert classify_step.output_schema is ns["ClassifyOutput"]
        assert issubclass(classify_step.output_schema, BaseModel)


# ============ Prompt Files ============


class TestPromptFiles:
    def test_all_prompts_exist(self):
        # Deployed workflows (static/workflows/)
        deployed = {
            "develop": [
                "00-classify.md", "01-explore.md", "02-plan.md",
                "03a-write-tests.md", "03b-verify-red.md", "03c-implement.md",
                "03d-verify-green.md", "03e-fix.md", "05-complete.md",
            ],
            "code-review": [
                "01-scope.md", "02-review.md", "03-synthesize.md",
            ],
            "testing": [
                "01-execute.md",
            ],
            "process-protocol": [
                "fix-review.md",
            ],
        }
        for workflow_name, prompts in deployed.items():
            for prompt in prompts:
                full = WORKFLOWS_DIR / workflow_name / "prompts" / prompt
                assert full.exists(), f"Missing prompt: {workflow_name}/prompts/{prompt}"

        # Plugin-only workflows (skills/)
        plugin_only = {
            "create-environment": [
                "01-generate.md", "02-generate-merge.md",
            ],
            "update-environment": [
                "01-delete-obsolete.md", "02-generate.md",
            ],
            "test-workflow": [
                "classify.md", "summarize.md",
                "session-step1.md", "session-step2.md",
                "parallel-check.md",
                "ask-single.md", "ask-group-step1.md",
                "ask-group-step2.md", "ask-parallel.md",
            ],
        }
        for workflow_name, prompts in plugin_only.items():
            for prompt in prompts:
                full = PLUGIN_SKILLS_DIR / workflow_name / "prompts" / prompt
                assert full.exists(), f"Missing prompt: {workflow_name}/prompts/{prompt}"


# ============ ask_user in LLMStep (TDD) ============


class TestLLMStepAskUser:
    def test_atomic_llm_step_asks_and_stops_in_noninteractive(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WORKFLOW_ENGINE_FAKE_SDK", "1")
        (tmp_path / "prompts").mkdir()
        (tmp_path / "prompts" / "ask.md").write_text(
            '[[ASK_USER {"message":"Choose mode","options":["quick","thorough"]}]]\n',
            encoding="utf-8",
        )

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            prompt_dir=str(tmp_path / "prompts"),
            io_handler=StopIOHandler({}),
        )
        step = LLMStep(
            name="ask-step",
            prompt="ask.md",
            tools=["ask_user"],
        )

        with pytest.raises(StopForInput) as exc:
            asyncio.run(execute_llm_step(step, ctx))

        stop = exc.value
        assert stop.step_name == "ask-step"
        assert stop.prompt_type == "input"
        assert stop.message == "Choose mode"
        assert stop.options == ["quick", "thorough"]
        assert stop.strict is False
        # Key must be scoped and stable: <step_exec_key>/ask:<fingerprint>
        assert stop.key.startswith("ask-step/ask:")

    def test_atomic_llm_step_resumes_when_answer_provided(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WORKFLOW_ENGINE_FAKE_SDK", "1")
        (tmp_path / "prompts").mkdir()
        (tmp_path / "prompts" / "ask.md").write_text(
            '[[ASK_USER {"message":"Pick","options":["a","b"]}]]\n',
            encoding="utf-8",
        )

        # First run: capture the stop to learn the question key.
        ctx1 = WorkflowContext(
            cwd=str(tmp_path),
            prompt_dir=str(tmp_path / "prompts"),
            io_handler=StopIOHandler({}),
        )
        step = LLMStep(name="ask-step", prompt="ask.md", tools=["ask_user"])
        with pytest.raises(StopForInput) as exc:
            asyncio.run(execute_llm_step(step, ctx1))
        key = exc.value.key

        # Second run: provide preset answer for that key.
        ctx2 = WorkflowContext(
            cwd=str(tmp_path),
            prompt_dir=str(tmp_path / "prompts"),
            io_handler=StopIOHandler({key: "b"}),
        )
        result = asyncio.run(execute_llm_step(step, ctx2))
        assert result.status == "success"
        # Fake backend should surface the answer deterministically.
        assert "b" in (result.output or "")

    def test_group_step_segments_uses_step_scoped_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WORKFLOW_ENGINE_FAKE_SDK", "1")
        (tmp_path / "prompts").mkdir()
        (tmp_path / "prompts" / "a.md").write_text("ok\n", encoding="utf-8")
        (tmp_path / "prompts" / "b.md").write_text(
            '[[ASK_USER {"message":"Confirm","options":["yes","no"]}]]\n',
            encoding="utf-8",
        )

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            prompt_dir=str(tmp_path / "prompts"),
            io_handler=StopIOHandler({}),
        )
        group = GroupBlock(
            name="g",
            llm_session_policy="step_segments",
            blocks=[
                LLMStep(name="a", prompt="a.md", tools=[]),
                LLMStep(name="b", prompt="b.md", tools=["ask_user"]),
            ],
        )

        with pytest.raises(StopForInput) as exc:
            asyncio.run(execute_group(group, ctx))

        stop = exc.value
        # Must be keyed to the actual step (b), not the group.
        assert stop.key.startswith("b/ask:")

    def test_parallel_each_records_completed_lanes_before_stop(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WORKFLOW_ENGINE_FAKE_SDK", "1")
        (tmp_path / "prompts").mkdir()
        (tmp_path / "prompts" / "ok.md").write_text("ok\n", encoding="utf-8")
        (tmp_path / "prompts" / "ask.md").write_text(
            '[[ASK_USER {"message":"Need input","options":["x","y"]}]]\n',
            encoding="utf-8",
        )

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            prompt_dir=str(tmp_path / "prompts"),
            variables={"items": ["a", "b"]},
            io_handler=StopIOHandler({}),
        )

        parallel = ParallelEachBlock(
            name="p",
            parallel_for="variables.items",
            template=[
                ConditionalBlock(
                    name="gate",
                    branches=[
                        Branch(
                            condition=lambda c: c.variables.get("item") == "b",
                            blocks=[LLMStep(name="ask", prompt="ask.md", tools=["ask_user"])],
                        )
                    ],
                    default=[LLMStep(name="ok", prompt="ok.md", tools=[])],
                )
            ],
        )

        with pytest.raises(StopForInput) as exc:
            asyncio.run(execute_parallel_each(parallel, ctx))

        stop = exc.value
        assert stop.key.startswith("par:p[i=1]/ask/ask:")
        # Lane 0 should already be recorded in parent results_scoped.
        assert "par:p[i=0]/ok" in ctx.results_scoped

    def test_prompts_are_nonempty(self):
        for base in (WORKFLOWS_DIR, PLUGIN_SKILLS_DIR):
            if not base.is_dir():
                continue
            for wf_dir in base.iterdir():
                prompt_dir = wf_dir / "prompts"
                if not prompt_dir.is_dir():
                    continue
                for md_file in prompt_dir.rglob("*.md"):
                    content = md_file.read_text()
                    assert len(content.strip()) > 0, f"Empty prompt: {md_file}"

    def test_prompts_have_headings(self):
        for base in (WORKFLOWS_DIR, PLUGIN_SKILLS_DIR):
            if not base.is_dir():
                continue
            for wf_dir in base.iterdir():
                prompt_dir = wf_dir / "prompts"
                if not prompt_dir.is_dir():
                    continue
                for md_file in prompt_dir.rglob("*.md"):
                    content = md_file.read_text()
                    assert content.startswith("#"), f"Prompt missing heading: {md_file}"


# ============ PromptStep Execution ============


class TestPromptStep:
    def test_confirm_with_preset(self):
        handler = PresetIOHandler({"confirm": "yes"})
        ctx = WorkflowContext(io_handler=handler)
        step = PromptStep(
            name="confirm",
            prompt_type="confirm",
            message="Proceed?",
            default="no",
            result_var="confirmed",
        )
        result = execute_prompt_step(step, ctx)
        assert result.status == "success"
        assert result.output == "yes"
        assert ctx.variables["confirmed"] == "yes"

    def test_choice_with_preset(self):
        handler = PresetIOHandler({"strategy": "2"})
        ctx = WorkflowContext(io_handler=handler)
        step = PromptStep(
            name="strategy",
            prompt_type="choice",
            message="Choose strategy:",
            options=["Resume", "Merge", "Fresh"],
            result_var="strategy",
        )
        result = execute_prompt_step(step, ctx)
        assert result.status == "success"
        # "2" maps to index 1 → "Merge"
        assert result.output == "Merge"
        assert ctx.variables["strategy"] == "Merge"
        assert result.structured_output == {"answer": "Merge", "index": 1}

    def test_choice_with_string_value(self):
        handler = PresetIOHandler({"strategy": "Fresh"})
        ctx = WorkflowContext(io_handler=handler)
        step = PromptStep(
            name="strategy",
            prompt_type="choice",
            message="Choose:",
            options=["Resume", "Merge", "Fresh"],
            result_var="strategy",
        )
        result = execute_prompt_step(step, ctx)
        assert result.output == "Fresh"
        assert result.structured_output == {"answer": "Fresh", "index": 2}

    def test_input_with_preset(self):
        handler = PresetIOHandler({"task-desc": "Add login"})
        ctx = WorkflowContext(io_handler=handler)
        step = PromptStep(
            name="task-desc",
            prompt_type="input",
            message="Describe the task:",
            result_var="task_description",
        )
        result = execute_prompt_step(step, ctx)
        assert result.status == "success"
        assert result.output == "Add login"
        assert ctx.variables["task_description"] == "Add login"

    def test_dry_run(self):
        ctx = WorkflowContext(dry_run=True)
        step = PromptStep(
            name="confirm",
            prompt_type="confirm",
            message="Proceed with 35 files?",
        )
        result = execute_prompt_step(step, ctx)
        assert result.status == "dry_run"
        # Dry-run simulates a deterministic answer (default or empty string).
        assert result.output in ("", "yes", "no")
        assert result.structured_output["dry_run"] is True
        assert "35 files" in result.structured_output["message"]

    def test_condition_skip(self):
        handler = PresetIOHandler({"confirm": "yes"})
        ctx = WorkflowContext(io_handler=handler, variables={"skip": True})
        step = PromptStep(
            name="confirm",
            prompt_type="confirm",
            message="Proceed?",
            condition=lambda ctx: not ctx.variables.get("skip"),
        )
        result = execute_prompt_step(step, ctx)
        assert result.status == "skipped"

    def test_default_when_no_answer(self):
        handler = PresetIOHandler({})  # no answers
        ctx = WorkflowContext(io_handler=handler)
        step = PromptStep(
            name="confirm",
            prompt_type="confirm",
            message="Proceed?",
            default="yes",
            result_var="confirmed",
        )
        result = execute_prompt_step(step, ctx)
        assert result.output == "yes"
        assert ctx.variables["confirmed"] == "yes"

    def test_in_workflow(self):
        handler = PresetIOHandler({"confirm": "yes"})
        wf = WorkflowDef(
            name="test-prompt-wf",
            description="test workflow with prompt",
            blocks=[
                ShellStep(name="detect", command="echo detected"),
                PromptStep(
                    name="confirm",
                    prompt_type="confirm",
                    message="Continue?",
                    default="no",
                    result_var="confirmed",
                ),
                ShellStep(
                    name="proceed",
                    command="echo proceeding",
                    condition=lambda ctx: ctx.variables.get("confirmed") == "yes",
                ),
                ShellStep(
                    name="skip-this",
                    command="echo skipped",
                    condition=lambda ctx: ctx.variables.get("confirmed") != "yes",
                ),
            ],
        )
        ctx = WorkflowContext(io_handler=handler, cwd="/tmp")
        results = asyncio.run(execute_workflow(wf, ctx))
        assert len(results) == 4
        assert results[0].status == "success"  # detect
        assert results[1].status == "success"  # confirm
        assert results[1].output == "yes"
        assert results[2].status == "success"  # proceed (condition true)
        assert results[3].status == "skipped"  # skip-this (condition false)

    def test_message_substitution(self):
        handler = PresetIOHandler({"confirm": "yes"})
        ctx = WorkflowContext(
            io_handler=handler,
            variables={"file_count": 35},
        )
        step = PromptStep(
            name="confirm",
            prompt_type="confirm",
            message="About to generate {{variables.file_count}} files. Proceed?",
            result_var="confirmed",
        )
        result = execute_prompt_step(step, ctx)
        assert result.status == "success"
        # The message was resolved but the answer is from the preset
        assert result.output == "yes"

    def test_key_used_for_results(self):
        handler = PresetIOHandler({"my-key": "yes"})
        ctx = WorkflowContext(io_handler=handler)
        step = PromptStep(
            name="Display Name",
            key="my-key",
            prompt_type="confirm",
            message="Proceed?",
        )
        result = execute_prompt_step(step, ctx)
        assert result.output == "yes"
        assert "my-key" in ctx.results
        assert ctx.results["my-key"].output == "yes"

    def test_invalid_choice_raises_error(self):
        """Invalid choice answer raises ValueError — strict validation."""
        handler = PresetIOHandler({"strategy": "the second one"})
        ctx = WorkflowContext(io_handler=handler)
        step = PromptStep(
            name="strategy",
            prompt_type="choice",
            message="Choose strategy:",
            options=["quick", "thorough", "exhaustive"],
            result_var="strategy",
        )
        import pytest
        with pytest.raises(ValueError, match="not a valid option"):
            execute_prompt_step(step, ctx)

    def test_invalid_choice_error_message_includes_options(self):
        """Error message lists valid options for debugging."""
        handler = PresetIOHandler({"strategy": "nonsense"})
        ctx = WorkflowContext(io_handler=handler)
        step = PromptStep(
            name="strategy",
            prompt_type="choice",
            message="Choose:",
            options=["Resume", "Merge", "Fresh"],
        )
        import pytest
        with pytest.raises(ValueError, match="Resume.*Merge.*Fresh"):
            execute_prompt_step(step, ctx)

    def test_valid_choice_no_error(self):
        """Valid answers pass through without error."""
        handler = PresetIOHandler({"strategy": "Merge"})
        ctx = WorkflowContext(io_handler=handler)
        step = PromptStep(
            name="strategy",
            prompt_type="choice",
            message="Choose:",
            options=["Resume", "Merge", "Fresh"],
            result_var="strategy",
        )
        result = execute_prompt_step(step, ctx)
        assert result.output == "Merge"
        assert result.structured_output == {"answer": "Merge", "index": 1}

    def test_non_strict_choice_allows_free_text(self):
        """Non-strict choice accepts answers not in options."""
        handler = PresetIOHandler({"strategy": "the second one"})
        ctx = WorkflowContext(io_handler=handler)
        step = PromptStep(
            name="strategy",
            prompt_type="choice",
            message="Choose:",
            options=["quick", "thorough"],
            strict=False,
            result_var="strategy",
        )
        result = execute_prompt_step(step, ctx)
        assert result.status == "success"
        assert result.output == "the second one"
        assert ctx.variables["strategy"] == "the second one"

    def test_strict_is_default(self):
        """PromptStep.strict defaults to True."""
        step = PromptStep(
            name="x", prompt_type="choice", message="Pick:", options=["a", "b"],
        )
        assert step.strict is True


# ============ StopForInput ============


class TestStopForInput:
    def test_stop_raises_on_unanswered(self):
        handler = StopIOHandler({})
        ctx = WorkflowContext(io_handler=handler)
        step = PromptStep(
            name="strategy",
            prompt_type="choice",
            message="Choose strategy:",
            options=["A", "B", "C"],
        )
        try:
            execute_prompt_step(step, ctx)
            assert False, "Should have raised StopForInput"
        except StopForInput as e:
            assert e.step_name == "strategy"
            assert e.prompt_type == "choice"
            assert e.options == ["A", "B", "C"]
            assert e.strict is True
            assert "Choose strategy" in e.message

    def test_stop_uses_preset_if_available(self):
        handler = StopIOHandler({"strategy": "B"})
        ctx = WorkflowContext(io_handler=handler)
        step = PromptStep(
            name="strategy",
            prompt_type="choice",
            message="Choose:",
            options=["A", "B", "C"],
            result_var="strategy",
        )
        result = execute_prompt_step(step, ctx)
        assert result.output == "B"
        assert ctx.variables["strategy"] == "B"

    def test_stop_propagates_through_workflow(self):
        handler = StopIOHandler({})
        wf = WorkflowDef(
            name="test",
            description="test",
            blocks=[
                ShellStep(name="detect", command="echo ok"),
                PromptStep(
                    name="ask",
                    prompt_type="confirm",
                    message="Continue?",
                ),
            ],
        )
        ctx = WorkflowContext(io_handler=handler, cwd="/tmp")
        try:
            asyncio.run(execute_workflow(wf, ctx))
            assert False, "Should have raised StopForInput"
        except StopForInput as e:
            assert e.step_name == "ask"
            # detect should have run before the stop
            assert "detect" in ctx.results
            assert ctx.results["detect"].status == "success"


# ============ Inject Results (resume) ============


class TestInjectResults:
    def test_skip_completed_blocks(self):
        ctx = WorkflowContext(cwd="/tmp")
        # Pre-inject a successful scoped result (resume semantics)
        injected = StepResult(
            name="detect",
            base="detect",
            results_key="detect",
            exec_key="detect",
            order=1,
            status="success",
            output="detected",
        )
        ctx.injected_results_scoped["detect"] = injected

        wf = WorkflowDef(
            name="test",
            description="test",
            blocks=[
                ShellStep(name="detect", command="echo should-not-rerun"),
                ShellStep(name="process", command="echo processed"),
            ],
        )
        results = asyncio.run(execute_workflow(wf, ctx))
        assert len(results) == 2
        # First result is the injected one (skipped re-execution)
        assert results[0].output == "detected"
        # Second ran normally
        assert results[1].status == "success"
        assert "processed" in results[1].output

    def test_continue_from_prompt_step(self):
        handler = PresetIOHandler({"confirm": "yes"})
        ctx = WorkflowContext(io_handler=handler, cwd="/tmp")
        # Inject prior detect result (resume semantics)
        injected = StepResult(
            name="detect",
            base="detect",
            results_key="detect",
            exec_key="detect",
            order=1,
            status="success",
            output="found 5 files",
        )
        ctx.injected_results_scoped["detect"] = injected

        wf = WorkflowDef(
            name="test",
            description="test",
            blocks=[
                ShellStep(name="detect", command="echo should-skip"),
                PromptStep(
                    name="confirm",
                    prompt_type="confirm",
                    message="Proceed?",
                    result_var="confirmed",
                ),
                ShellStep(
                    name="generate",
                    command="echo generating",
                    condition=lambda ctx: ctx.variables.get("confirmed") == "yes",
                ),
            ],
        )
        results = asyncio.run(execute_workflow(wf, ctx))
        assert len(results) == 3
        # detect was skipped (injected)
        assert results[0].output == "found 5 files"
        # confirm ran with preset
        assert results[1].output == "yes"
        # generate ran because confirmed == "yes"
        assert results[2].status == "success"
        assert "generating" in results[2].output

    def test_failed_results_not_skipped(self):
        ctx = WorkflowContext(cwd="/tmp")
        # Inject a failed result — should re-execute
        injected = StepResult(
            name="detect",
            base="detect",
            results_key="detect",
            exec_key="detect",
            order=1,
            status="failure",
            error="bad",
        )
        ctx.injected_results_scoped["detect"] = injected

        wf = WorkflowDef(
            name="test",
            description="test",
            blocks=[
                ShellStep(name="detect", command="echo rerun"),
            ],
        )
        results = asyncio.run(execute_workflow(wf, ctx))
        assert results[0].status == "success"
        assert "rerun" in results[0].output

    def test_group_segment_skips_cached_steps(self, tmp_path, monkeypatch):
        """GroupBlock step_segments must skip SDK session when all steps are cached."""
        monkeypatch.setenv("WORKFLOW_ENGINE_FAKE_SDK", "1")
        (tmp_path / "prompts").mkdir()
        (tmp_path / "prompts" / "a.md").write_text("step a\n", encoding="utf-8")
        (tmp_path / "prompts" / "b.md").write_text("step b\n", encoding="utf-8")

        ctx = WorkflowContext(cwd=str(tmp_path), prompt_dir=str(tmp_path / "prompts"))
        # Inject cached results for both steps in the segment
        for name in ("a", "b"):
            ctx.injected_results_scoped[name] = StepResult(
                name=name, base=name, results_key=name, exec_key=name,
                order=1, status="success", output=f"cached-{name}",
            )

        group = GroupBlock(
            name="g",
            llm_session_policy="step_segments",
            blocks=[
                LLMStep(name="a", prompt="a.md", tools=[]),
                LLMStep(name="b", prompt="b.md", tools=[]),
            ],
        )
        results = asyncio.run(execute_group(group, ctx))
        assert len(results) == 2
        assert results[0].output == "cached-a"
        assert results[1].output == "cached-b"
        # Both should be in ctx.results
        assert ctx.results["a"].output == "cached-a"
        assert ctx.results["b"].output == "cached-b"

    def test_group_segment_ask_user_cached_skips_reask(self, tmp_path, monkeypatch):
        """GroupBlock with ask_user steps must not re-trigger ask_user when cached."""
        monkeypatch.setenv("WORKFLOW_ENGINE_FAKE_SDK", "1")
        (tmp_path / "prompts").mkdir()
        (tmp_path / "prompts" / "ask.md").write_text(
            '[[ASK_USER {"message":"Pick","options":["x","y"]}]]\n', encoding="utf-8"
        )
        (tmp_path / "prompts" / "use.md").write_text("use answer\n", encoding="utf-8")

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            prompt_dir=str(tmp_path / "prompts"),
            io_handler=StopIOHandler({}),
        )
        # Inject cached results — simulating resume after ask_user was answered
        ctx.injected_results_scoped["ask"] = StepResult(
            name="ask", base="ask", results_key="ask", exec_key="ask",
            order=1, status="success", output="answer: x",
        )
        ctx.injected_results_scoped["use"] = StepResult(
            name="use", base="use", results_key="use", exec_key="use",
            order=2, status="success", output="used answer",
        )

        group = GroupBlock(
            name="g",
            llm_session_policy="step_segments",
            blocks=[
                LLMStep(name="ask", prompt="ask.md", tools=["ask_user"]),
                LLMStep(name="use", prompt="use.md", tools=[]),
            ],
        )
        # Should NOT raise StopForInput — both steps are cached
        results = asyncio.run(execute_group(group, ctx))
        assert len(results) == 2
        assert results[0].output == "answer: x"
        assert results[1].output == "used answer"


# ============ ConditionalBlock ============


class TestConditionalBlock:
    def test_first_branch_match(self):
        ctx = WorkflowContext(variables={"strategy": "fresh"}, dry_run=True, cwd="/tmp")
        block = ConditionalBlock(
            name="branch",
            branches=[
                Branch(
                    condition=lambda ctx: ctx.variables.get("strategy") == "fresh",
                    blocks=[ShellStep(name="fresh-step", command="echo fresh")],
                ),
                Branch(
                    condition=lambda ctx: ctx.variables.get("strategy") == "merge",
                    blocks=[ShellStep(name="merge-step", command="echo merge")],
                ),
            ],
            default=[ShellStep(name="default-step", command="echo default")],
        )
        results = asyncio.run(execute_conditional(block, ctx))
        assert len(results) == 1
        assert results[0].name == "fresh-step"
        assert results[0].status == "dry_run"

    def test_second_branch_match(self):
        ctx = WorkflowContext(variables={"strategy": "merge"}, dry_run=True, cwd="/tmp")
        block = ConditionalBlock(
            name="branch",
            branches=[
                Branch(
                    condition=lambda ctx: ctx.variables.get("strategy") == "fresh",
                    blocks=[ShellStep(name="fresh-step", command="echo fresh")],
                ),
                Branch(
                    condition=lambda ctx: ctx.variables.get("strategy") == "merge",
                    blocks=[ShellStep(name="merge-step", command="echo merge")],
                ),
            ],
            default=[ShellStep(name="default-step", command="echo default")],
        )
        results = asyncio.run(execute_conditional(block, ctx))
        assert len(results) == 1
        assert results[0].name == "merge-step"

    def test_default_branch(self):
        ctx = WorkflowContext(variables={"strategy": "unknown"}, dry_run=True, cwd="/tmp")
        block = ConditionalBlock(
            name="branch",
            branches=[
                Branch(
                    condition=lambda ctx: ctx.variables.get("strategy") == "fresh",
                    blocks=[ShellStep(name="fresh-step", command="echo fresh")],
                ),
            ],
            default=[ShellStep(name="default-step", command="echo default")],
        )
        results = asyncio.run(execute_conditional(block, ctx))
        assert len(results) == 1
        assert results[0].name == "default-step"

    def test_no_match_empty_default(self):
        ctx = WorkflowContext(variables={"strategy": "unknown"}, dry_run=True, cwd="/tmp")
        block = ConditionalBlock(
            name="branch",
            branches=[
                Branch(
                    condition=lambda ctx: ctx.variables.get("strategy") == "fresh",
                    blocks=[ShellStep(name="fresh-step", command="echo fresh")],
                ),
            ],
        )
        results = asyncio.run(execute_conditional(block, ctx))
        assert results == []

    def test_condition_skip(self):
        ctx = WorkflowContext(variables={"skip": True}, dry_run=True, cwd="/tmp")
        block = ConditionalBlock(
            name="branch",
            branches=[
                Branch(
                    condition=lambda ctx: True,
                    blocks=[ShellStep(name="step", command="echo hi")],
                ),
            ],
            condition=lambda ctx: not ctx.variables.get("skip"),
        )
        results = asyncio.run(execute_conditional(block, ctx))
        assert len(results) == 1
        assert results[0].status == "skipped"

    def test_nested_blocks(self):
        ctx = WorkflowContext(variables={"strategy": "fresh"}, dry_run=True, cwd="/tmp")
        block = ConditionalBlock(
            name="branch",
            branches=[
                Branch(
                    condition=lambda ctx: ctx.variables.get("strategy") == "fresh",
                    blocks=[
                        ShellStep(name="step-1", command="echo one"),
                        ShellStep(name="step-2", command="echo two"),
                    ],
                ),
            ],
        )
        results = asyncio.run(execute_conditional(block, ctx))
        assert len(results) == 2
        assert results[0].name == "step-1"
        assert results[1].name == "step-2"

    def test_in_workflow(self):
        handler = PresetIOHandler({"confirm": "yes"})
        wf = WorkflowDef(
            name="test-conditional-wf",
            description="test conditional in workflow",
            blocks=[
                PromptStep(
                    name="confirm",
                    prompt_type="confirm",
                    message="Proceed?",
                    default="no",
                    result_var="confirmed",
                ),
                ConditionalBlock(
                    name="branch",
                    branches=[
                        Branch(
                            condition=lambda ctx: ctx.variables.get("confirmed") == "yes",
                            blocks=[ShellStep(name="go", command="echo going")],
                        ),
                    ],
                    default=[ShellStep(name="abort", command="echo aborting")],
                ),
            ],
        )
        ctx = WorkflowContext(io_handler=handler, cwd="/tmp")
        results = asyncio.run(execute_workflow(wf, ctx))
        assert len(results) == 2
        assert results[0].output == "yes"
        assert results[1].name == "go"
        assert results[1].status == "success"


# ============ ShellStep result_var ============


class TestShellStepResultVar:
    def test_json_stdout_stored(self):
        ctx = WorkflowContext(cwd="/tmp")
        step = ShellStep(
            name="json-out",
            command='echo \'{"exists": true, "count": 5}\'',
            result_var="parsed",
        )
        result = execute_shell(step, ctx)
        assert result.status == "success"
        assert ctx.variables["parsed"] == {"exists": True, "count": 5}
        assert result.structured_output == {"exists": True, "count": 5}

    def test_non_json_stdout_not_stored(self):
        ctx = WorkflowContext(cwd="/tmp")
        step = ShellStep(
            name="plain-out",
            command="echo hello world",
            result_var="parsed",
        )
        result = execute_shell(step, ctx)
        assert result.status == "success"
        assert "parsed" not in ctx.variables

    def test_no_result_var_no_parsing(self):
        ctx = WorkflowContext(cwd="/tmp")
        step = ShellStep(
            name="normal",
            command='echo \'{"key": "value"}\'',
        )
        result = execute_shell(step, ctx)
        assert result.status == "success"
        assert "key" not in ctx.variables

    def test_result_var_dry_run(self):
        ctx = WorkflowContext(cwd="/tmp", dry_run=True)
        step = ShellStep(
            name="dry",
            command='echo \'{"key": "value"}\'',
            result_var="parsed",
        )
        result = execute_shell(step, ctx)
        assert result.status == "dry_run"
        assert "parsed" not in ctx.variables

    def test_result_var_on_failure(self):
        ctx = WorkflowContext(cwd="/tmp")
        step = ShellStep(
            name="fail",
            command="exit 1",
            result_var="parsed",
        )
        result = execute_shell(step, ctx)
        assert result.status == "failure"
        assert "parsed" not in ctx.variables


# ============ Create-Environment Workflow ============


class TestCreateEnvironmentWorkflow:
    def test_loads(self):
        wf = load_workflow(PLUGIN_SKILLS_DIR / "create-environment")
        assert wf.name == "create-environment"
        assert len(wf.blocks) > 0

    def test_has_conditional_block(self):
        wf = load_workflow(PLUGIN_SKILLS_DIR / "create-environment")
        conditional_blocks = [b for b in wf.blocks if type(b).__name__ == "ConditionalBlock"]
        assert len(conditional_blocks) == 1
        assert conditional_blocks[0].name == "execute-strategy"

    def test_has_prompt_steps(self):
        wf = load_workflow(PLUGIN_SKILLS_DIR / "create-environment")
        prompt_steps = [b for b in wf.blocks if type(b).__name__ == "PromptStep"]
        assert len(prompt_steps) == 2
        names = {s.name for s in prompt_steps}
        assert "strategy" in names
        assert "confirm" in names


# ============ Test-Workflow Full Execution ============


class TestTestWorkflowExecution:
    def test_shell_only_run(self, tmp_path):
        """Phases 1-9, 14-15 execute; phases 10-13 skipped (no enable_llm)."""
        wf = load_workflow(PLUGIN_SKILLS_DIR / "test-workflow")
        sub_dir = PLUGIN_SKILLS_DIR / "test-workflow" / "sub-workflows"
        registry = discover_workflows(sub_dir)
        registry[wf.name] = wf

        handler = PresetIOHandler({
            "mode": "quick",
            "final-decision": "accept",
            "confirm-results": "yes",
        })
        ctx = WorkflowContext(
            io_handler=handler,
            cwd=str(tmp_path),
            variables={"run_id": "test123"},
        )
        results = asyncio.run(execute_workflow(wf, ctx, registry=registry))

        names = [r.name for r in results]
        statuses = {r.name: r.status for r in results}

        # Phase 1: detect
        assert statuses["detect"] == "success"
        assert ctx.results["detect"].structured_output == {"items": ["alpha", "beta", "gamma"], "count": 3}

        # Phase 3: quick branch taken
        assert "quick-run" in names
        assert statuses["quick-run"] == "success"

        # Phase 5: risky-step fails, recovery runs, skip-on-success skipped
        assert statuses["risky-step"] == "failure"
        assert statuses["recovery"] == "success"
        assert statuses["skip-on-success"] == "skipped"

        # Phase 6: counter dir created
        assert statuses["setup-counter-dir"] == "success"

        # Phase 7: retry succeeds after 3 attempts
        flaky_results = [r for r in results if r.name == "flaky-cmd"]
        assert len(flaky_results) == 3  # 2 failures + 1 success
        assert flaky_results[-1].status == "success"

        # Phase 8: sub-workflow ran
        assert "call-helper.helper-echo" in ctx.results
        assert "call-helper.helper-transform" in ctx.results

        # Phase 9: loop+retry — first item retries (fail + success), subsequent
        # items execute independently (no implicit caching)
        item_flaky = [r for r in results if r.name == "item-flaky"]
        assert len(item_flaky) == 6  # each item: 1 fail + 1 success

        # Phases 10-13: all skipped (no enable_llm)
        assert statuses.get("llm-classify") == "skipped"
        assert statuses.get("llm-summarize") == "skipped"
        assert statuses.get("llm-session") == "skipped"
        assert statuses.get("parallel-gate") == "skipped"

        # Phase 14: key≠name — stored under "final-decision" not "final-prompt"
        assert "final-decision" in ctx.results
        assert ctx.results["final-decision"].output == "accept"
        assert ctx.variables["decision"] == "accept"

        # Phase 15: finalize + cleanup ran
        assert statuses["finalize"] == "success"
        assert statuses["cleanup"] == "success"

    def test_dry_run(self):
        """Dry run produces dry_run statuses for shell/LLM steps.

        Loops and retries that depend on prior structured_output will fail
        with 'not a list' since dry-run shells don't produce real output.
        """
        wf = load_workflow(PLUGIN_SKILLS_DIR / "test-workflow")
        sub_dir = PLUGIN_SKILLS_DIR / "test-workflow" / "sub-workflows"
        registry = discover_workflows(sub_dir)
        registry[wf.name] = wf

        handler = PresetIOHandler({
            "mode": "quick",
            "final-decision": "accept",
            "confirm-results": "yes",
        })
        ctx = WorkflowContext(
            io_handler=handler,
            cwd="/tmp",
            dry_run=True,
            variables={"run_id": "dry123", "enable_llm": True},
        )
        results = asyncio.run(execute_workflow(wf, ctx, registry=registry))
        statuses = {r.name: r.status for r in results}

        # Direct shell steps get dry_run
        assert statuses["detect"] == "dry_run"
        assert statuses["setup-counter-dir"] == "dry_run"

        # LLM steps also get dry_run (with enable_llm=True)
        assert statuses["llm-classify"] == "dry_run"
        assert statuses["llm-summarize"] == "dry_run"

        # Prompts return dry_run (deterministic simulated answers)
        assert statuses.get("confirm-results") == "dry_run"

        # Finalize is dry_run: prompt simulation makes its condition deterministic.
        assert statuses["finalize"] == "dry_run"


# ============ _parse_kv ============


class TestParseKv:
    def test_simple_kv(self):
        """Simple key=value works."""
        from importlib import import_module
        runner_code = (SCRIPTS_DIR / "runner.py").read_text(encoding="utf-8")
        runner_code = re.sub(r"from \.+\w+ import .+", "", runner_code)
        runner_code = re.sub(r"from \.+\w+ import \(.*?\)", "", runner_code, flags=re.DOTALL)
        ns: dict = {}
        exec(compile(runner_code, "runner.py", "exec"), ns)
        parse_kv = ns["_parse_kv"]
        assert parse_kv(["mode=thorough"], "answer") == {"mode": "thorough"}

    def test_scoped_key_with_equals(self):
        """Keys containing '=' (e.g. par:block[i=0]/step) must be parsed correctly."""
        runner_code = (SCRIPTS_DIR / "runner.py").read_text(encoding="utf-8")
        runner_code = re.sub(r"from \.+\w+ import .+", "", runner_code)
        runner_code = re.sub(r"from \.+\w+ import \(.*?\)", "", runner_code, flags=re.DOTALL)
        ns: dict = {}
        exec(compile(runner_code, "runner.py", "exec"), ns)
        parse_kv = ns["_parse_kv"]
        result = parse_kv(
            ["par:parallel-ask-checks[i=0]/ask-check/ask:2ed9b7ef3f=yes"],
            "answer",
        )
        assert result == {"par:parallel-ask-checks[i=0]/ask-check/ask:2ed9b7ef3f": "yes"}


# ============ Runner --output flag ============


class TestOutputFlag:
    def test_output_to_file(self, tmp_path):
        """--output writes all stdout to the specified file."""
        import subprocess
        import sys

        output_file = tmp_path / "out.txt"
        runner_path = str(SCRIPTS_DIR.parent / "run.py")
        result = subprocess.run(
            [sys.executable, runner_path, "test-workflow",
             "--workflow-dir", str(PLUGIN_SKILLS_DIR / "test-workflow"),
             "--workflow-dir", str(PLUGIN_SKILLS_DIR / "test-workflow" / "sub-workflows"),
             "--dry-run",
             "--answer", "mode=quick",
             "--answer", "final-decision=accept",
             "--answer", "confirm-results=yes",
             "--output", str(output_file)],
            capture_output=True, text=True, cwd=str(tmp_path),
        )
        # stdout should be empty (redirected to file)
        assert result.stdout == ""
        # file should contain the workflow output
        file_content = output_file.read_text(encoding="utf-8")
        assert "Running workflow: test-workflow" in file_content
        assert "Variables:" in file_content

    def test_output_resume_command_includes_cat(self, tmp_path):
        """resume_command in question.json includes --output and ; cat."""
        import subprocess
        import sys

        # Minimal workflow with a PromptStep that triggers StopForInput
        wf_dir = tmp_path / "ask-wf"
        wf_dir.mkdir()
        (wf_dir / "workflow.py").write_text(
            'WORKFLOW = WorkflowDef(\n'
            '  name="ask-wf",\n'
            '  description="test",\n'
            '  blocks=[\n'
            '    PromptStep(name="q", prompt_type="choice", message="Pick?", options=["a","b"]),\n'
            '  ],\n'
            ')\n',
            encoding="utf-8",
        )

        output_file = tmp_path / "out.txt"
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR.parent / "run.py"), "ask-wf",
             "--workflow-dir", str(wf_dir),
             "--output", str(output_file)],
            capture_output=True, text=True, cwd=str(tmp_path),
            input="",  # non-TTY
        )
        assert result.returncode == 0
        file_content = output_file.read_text(encoding="utf-8")
        assert "workflow_question" in file_content
        # resume_command should include --output and ; cat
        assert "--output" in file_content
        assert "; cat" in file_content


# ============ Runner run_id Injection ============


class TestRunIdInjection:
    def test_run_id_set_on_fresh_run(self):
        """runner.py injects run_id into variables on fresh run."""
        import subprocess
        import sys

        runner_path = str(SCRIPTS_DIR.parent / "run.py")
        result = subprocess.run(
            [sys.executable, runner_path, "test-workflow",
             "--workflow-dir", str(PLUGIN_SKILLS_DIR / "test-workflow"),
             "--workflow-dir", str(PLUGIN_SKILLS_DIR / "test-workflow" / "sub-workflows"),
             "--dry-run",
             "--answer", "mode=quick",
             "--answer", "final-decision=accept",
             "--answer", "confirm-results=yes"],
            capture_output=True, text=True, cwd="/tmp",
        )
        # Dry-run returns 1 due to loop failures (no structured_output),
        # but we just verify run_id appears in the Variables output
        assert "run_id" in result.stdout
        assert "Variables:" in result.stdout


# ============ Runner resume drift policy ============


class TestRunnerResumeDriftPolicy:
    def test_scoped_prompt_key_printed_on_stop(self, tmp_path):
        """When a PromptStep occurs inside a loop, runner prints the fully-scoped key."""
        import subprocess
        import sys

        wf_dir = tmp_path / "my-workflow"
        wf_dir.mkdir()
        (wf_dir / "workflow.py").write_text(
            'WORKFLOW = WorkflowDef(\n'
            '  name="my-workflow",\n'
            '  description="test",\n'
            '  blocks=[\n'
            '    ShellStep(\n'
            '      name="detect",\n'
            '      command="echo \'{\\"items\\":[\\"a\\"]}\'",\n'
            '      result_var="detect_json",\n'
            '    ),\n'
            '    LoopBlock(\n'
            '      name="items",\n'
            '      loop_over="results.detect.structured_output.items",\n'
            '      loop_var="item",\n'
            '      blocks=[\n'
            '        PromptStep(name="confirm", prompt_type="confirm", message="Continue?", default="yes"),\n'
            '      ],\n'
            '    ),\n'
            '  ],\n'
            ')\n'
        )

        runner_path = str(SCRIPTS_DIR.parent / "run.py")
        result = subprocess.run(
            [
                sys.executable,
                runner_path,
                "my-workflow",
                "--workflow-dir",
                str(wf_dir),
                "--cwd",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0
        # Must include structured question block with scoped key
        assert '"workflow_question"' in result.stdout
        assert "loop:items[i=0]/confirm" in result.stdout
        assert "Present the question above to the user" in result.stdout

    def test_stop_output_includes_validation_instructions(self, tmp_path):
        """StopForInput output includes validation rules when options are present."""
        import subprocess
        import sys

        wf_dir = tmp_path / "val-wf"
        wf_dir.mkdir()
        (wf_dir / "workflow.py").write_text(
            'WORKFLOW = WorkflowDef(\n'
            '  name="val-wf",\n'
            '  description="test",\n'
            '  blocks=[\n'
            '    PromptStep(\n'
            '      name="strategy",\n'
            '      prompt_type="choice",\n'
            '      message="Choose:",\n'
            '      options=["quick", "thorough"],\n'
            '    ),\n'
            '  ],\n'
            ')\n'
        )
        runner_path = str(SCRIPTS_DIR.parent / "run.py")
        result = subprocess.run(
            [
                sys.executable,
                runner_path,
                "val-wf",
                "--workflow-dir",
                str(wf_dir),
                "--cwd",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0
        assert "Valid answers (exact values only):" in result.stdout
        assert "Re-ask the question" in result.stdout
        assert "Stop the workflow" in result.stdout

    def test_resume_refuses_if_workflow_changed(self, tmp_path):
        """Strict resume: if workflow source changes, resume fails with clear error."""
        import subprocess
        import sys

        wf_dir = tmp_path / "drift-wf"
        wf_dir.mkdir()
        wf_path = wf_dir / "workflow.py"
        wf_path.write_text(
            'WORKFLOW = WorkflowDef(\n'
            '  name="drift-wf",\n'
            '  description="test",\n'
            '  blocks=[\n'
            '    PromptStep(name="confirm", prompt_type="confirm", message="Continue?", default="yes"),\n'
            '    ShellStep(name="done", command="echo done"),\n'
            '  ],\n'
            ')\n'
        )

        runner_path = str(SCRIPTS_DIR.parent / "run.py")
        stopped = subprocess.run(
            [
                sys.executable,
                runner_path,
                "drift-wf",
                "--workflow-dir",
                str(wf_dir),
                "--cwd",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        assert stopped.returncode == 0
        # Find created checkpoint/run_id
        ws_root = tmp_path / ".workflow-state"
        run_id = next(ws_root.iterdir()).name

        # Modify workflow.py after checkpoint is created (drift)
        wf_path.write_text(wf_path.read_text() + "\n# drift\n")

        resumed = subprocess.run(
            [
                sys.executable,
                runner_path,
                "resume",
                "--cwd",
                str(tmp_path),
                "--run-id",
                run_id,
                "--answer",
                "confirm=yes",
            ],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        assert resumed.returncode == 1
        assert "refusing to resume" in resumed.stderr.lower()


# ============ Progress Feedback (_emit) ============


class TestEmitFeedback:
    def test_emit_indentation_matches_scope_depth(self, capsys):
        """_emit indentation is 2 spaces per scope level (plus base indent)."""
        ctx = WorkflowContext(cwd="/tmp")
        _emit(ctx, "no scope")
        ctx.push_scope("loop:items[i=0]")
        _emit(ctx, "depth 1")
        ctx.push_scope("retry:r[attempt=1]")
        _emit(ctx, "depth 2")
        ctx.pop_scope()
        ctx.pop_scope()
        out = capsys.readouterr().out
        lines = [l for l in out.split("\n") if l.strip()]
        assert lines[0] == "  no scope"       # depth 0 → 2 spaces
        assert lines[1] == "    depth 1"       # depth 1 → 4 spaces
        assert lines[2] == "      depth 2"     # depth 2 → 6 spaces

    def test_shell_step_emits_progress(self, capsys, tmp_path):
        """ShellStep prints start/success lines to stdout."""
        ctx = WorkflowContext(cwd=str(tmp_path))
        step = ShellStep(name="hello", command="echo hi")
        execute_shell(step, ctx)
        out = capsys.readouterr().out
        assert "\u25b6 [ShellStep] hello" in out
        assert "\u2713 hello" in out

    def test_shell_step_emits_failure(self, capsys, tmp_path):
        """Failed ShellStep prints failure marker."""
        ctx = WorkflowContext(cwd=str(tmp_path))
        step = ShellStep(name="bad", command="exit 1")
        execute_shell(step, ctx)
        out = capsys.readouterr().out
        assert "\u2717 bad" in out

    def test_prompt_step_emits_answer(self, capsys):
        """PromptStep prints question, options, and answer in questionnaire format."""
        handler = PresetIOHandler({"pick": "b"})
        ctx = WorkflowContext(cwd="/tmp", io_handler=handler)
        step = PromptStep(
            name="pick", prompt_type="choice",
            message="Choose one:", options=["a", "b", "c"], default="a",
        )
        execute_prompt_step(step, ctx)
        out = capsys.readouterr().out
        lines = [l for l in out.split("\n") if l.strip()]
        assert "[PromptStep] pick" in lines[0]
        assert "Choose one:" in lines[1]
        assert "1. a" in lines[2]
        assert "2. b" in lines[3]
        assert "3. c" in lines[4]
        assert "\u2192 b" in lines[5]

    def test_prompt_step_confirm_no_options(self, capsys):
        """Confirm PromptStep shows question and answer without numbered options."""
        handler = PresetIOHandler({"ask": "yes"})
        ctx = WorkflowContext(cwd="/tmp", io_handler=handler)
        step = PromptStep(name="ask", prompt_type="confirm", message="Continue?", default="yes")
        execute_prompt_step(step, ctx)
        out = capsys.readouterr().out
        assert "[PromptStep] ask" in out
        assert "Continue?" in out
        assert "\u2192 yes" in out
        # No numbered options for confirm type
        assert "1." not in out

    def test_loop_emits_item_count(self, capsys, tmp_path):
        """LoopBlock prints item count and per-item progress."""
        ctx = WorkflowContext(cwd=str(tmp_path), variables={"items": ["a", "b"]})
        ctx.results["src"] = StepResult(name="src", structured_output={"items": ["a", "b"]})
        block = LoopBlock(
            name="myloop",
            loop_over="results.src.structured_output.items",
            loop_var="item",
            blocks=[ShellStep(name="echo", command="echo ok")],
        )
        asyncio.run(execute_loop(block, ctx))
        out = capsys.readouterr().out
        assert "[LoopBlock] myloop (2 items)" in out
        assert "[1/2]" in out
        assert "[2/2]" in out


# ============ File Logging ============


class TestFileLogging:
    def test_logger_called_during_shell_step(self, tmp_path):
        """Logger records INFO messages during shell step execution."""
        import logging

        wf_logger = logging.getLogger("workflow-engine")
        log_file = tmp_path / "test.log"
        handler = logging.FileHandler(str(log_file), encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        wf_logger.addHandler(handler)
        wf_logger.setLevel(logging.DEBUG)

        try:
            ctx = WorkflowContext(cwd=str(tmp_path))
            step = ShellStep(name="logged", command="echo hello")
            execute_shell(step, ctx)
            handler.flush()

            log_content = log_file.read_text()
            assert "[logged] ShellStep start" in log_content
            assert "[logged] ShellStep success" in log_content
            assert "hello" in log_content
        finally:
            wf_logger.removeHandler(handler)
            handler.close()

    def test_runner_creates_log_file(self, tmp_path):
        """runner.py creates execution.log in the state directory."""
        import subprocess
        import sys

        wf_dir = tmp_path / "log-wf"
        wf_dir.mkdir()
        (wf_dir / "workflow.py").write_text(
            'WORKFLOW = WorkflowDef(\n'
            '  name="log-wf",\n'
            '  description="test logging",\n'
            '  blocks=[\n'
            '    ShellStep(name="hello", command="echo hi"),\n'
            '  ],\n'
            ')\n'
        )

        runner_path = str(SCRIPTS_DIR.parent / "run.py")
        result = subprocess.run(
            [
                sys.executable,
                runner_path,
                "log-wf",
                "--workflow-dir",
                str(wf_dir),
                "--cwd",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0
        assert "Log:" in result.stdout
        assert "Log saved:" in result.stdout

        # Verify log file exists and has content
        ws_root = tmp_path / ".workflow-state"
        log_files = list(ws_root.glob("*/execution.log"))
        assert len(log_files) == 1
        log_content = log_files[0].read_text()
        assert "[hello] ShellStep start" in log_content
        assert "[hello] ShellStep success" in log_content
