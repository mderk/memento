"""Tests for the YAML workflow compiler.

Tests expression parser, block compilation, module resolution, and full round-trip.
"""

from pathlib import Path

import pytest

from conftest import _types_ns, _state_ns, _compiler_ns

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "compiler-test"

# Types
WorkflowContext = _types_ns["WorkflowContext"]
WorkflowDef = _types_ns["WorkflowDef"]
StepResult = _types_ns["StepResult"]
LLMStep = _types_ns["LLMStep"]
ShellStep = _types_ns["ShellStep"]
PromptStep = _types_ns["PromptStep"]
GroupBlock = _types_ns["GroupBlock"]
LoopBlock = _types_ns["LoopBlock"]
RetryBlock = _types_ns["RetryBlock"]
ConditionalBlock = _types_ns["ConditionalBlock"]
SubWorkflow = _types_ns["SubWorkflow"]
ParallelEachBlock = _types_ns["ParallelEachBlock"]
Branch = _types_ns["Branch"]

# Compiler
compile_expression = _compiler_ns["compile_expression"]
compile_block = _compiler_ns["compile_block"]
compile_workflow = _compiler_ns["compile_workflow"]
_load_modules = _compiler_ns["_load_modules"]
_resolve_ref = _compiler_ns["_resolve_ref"]
_tokenize = _compiler_ns["_tokenize"]

# State (for action builders)
_build_shell_action = _state_ns["_build_shell_action"]
_build_prompt_action = _state_ns["_build_prompt_action"]
_build_dry_run_action = _state_ns["_build_dry_run_action"]
substitute = _state_ns["substitute"]
RunState = _state_ns["RunState"]
Frame = _state_ns["Frame"]


def _make_state(cwd="/test", **kw):
    """Create a minimal RunState for action builder tests."""
    wf = WorkflowDef(name="test", description="test")
    ctx = WorkflowContext(variables=kw, cwd=cwd)
    return RunState(
        run_id="test-run",
        ctx=ctx,
        stack=[Frame(block=wf)],
        registry={},
    )


# ============ Expression Parser ============


class TestExpressionParser:
    def test_equality(self):
        cond = compile_expression('results.mode.output == "thorough"')
        ctx = WorkflowContext()
        ctx.results["mode"] = StepResult(name="mode", output="thorough")
        assert cond(ctx) is True

    def test_equality_false(self):
        cond = compile_expression('results.mode.output == "thorough"')
        ctx = WorkflowContext()
        ctx.results["mode"] = StepResult(name="mode", output="quick")
        assert cond(ctx) is False

    def test_inequality(self):
        cond = compile_expression('variables.x != "bad"')
        ctx = WorkflowContext(variables={"x": "good"})
        assert cond(ctx) is True

    def test_inequality_false(self):
        cond = compile_expression('variables.x != "bad"')
        ctx = WorkflowContext(variables={"x": "bad"})
        assert cond(ctx) is False

    def test_null_coalesce_with_equality(self):
        cond = compile_expression('variables.confirmed ?? "yes" == "yes"')
        # When variable is missing → uses default "yes"
        ctx = WorkflowContext()
        assert cond(ctx) is True
        # When variable is set to "no"
        ctx2 = WorkflowContext(variables={"confirmed": "no"})
        assert cond(ctx2) is False
        # When variable is set to "yes"
        ctx3 = WorkflowContext(variables={"confirmed": "yes"})
        assert cond(ctx3) is True

    def test_in_operator(self):
        cond = compile_expression('variables.action in ["Full regeneration", "All updates"]')
        ctx = WorkflowContext(variables={"action": "Full regeneration"})
        assert cond(ctx) is True
        ctx2 = WorkflowContext(variables={"action": "Partial"})
        assert cond(ctx2) is False

    def test_in_with_none_lhs(self):
        cond = compile_expression('variables.missing in ["a", "b"]')
        ctx = WorkflowContext()
        assert cond(ctx) is False

    def test_bare_truthy(self):
        cond = compile_expression('variables.enabled')
        assert cond(WorkflowContext(variables={"enabled": True})) is True
        assert cond(WorkflowContext(variables={"enabled": False})) is False
        assert cond(WorkflowContext(variables={"enabled": "yes"})) is True
        assert cond(WorkflowContext()) is False  # missing → None → falsy

    def test_not_operator(self):
        cond = compile_expression('not variables.fast_track')
        assert cond(WorkflowContext(variables={"fast_track": True})) is False
        assert cond(WorkflowContext(variables={"fast_track": False})) is True
        assert cond(WorkflowContext()) is True  # missing → None → not None → True

    def test_and_operator(self):
        cond = compile_expression('variables.a == "x" and variables.b == "y"')
        assert cond(WorkflowContext(variables={"a": "x", "b": "y"})) is True
        assert cond(WorkflowContext(variables={"a": "x", "b": "z"})) is False

    def test_or_operator(self):
        cond = compile_expression('variables.enable_llm == true or results.mode.output == "thorough"')
        ctx1 = WorkflowContext(variables={"enable_llm": True})
        assert cond(ctx1) is True
        ctx2 = WorkflowContext()
        ctx2.results["mode"] = StepResult(name="mode", output="thorough")
        assert cond(ctx2) is True
        ctx3 = WorkflowContext(variables={"enable_llm": False})
        assert cond(ctx3) is False

    def test_parentheses(self):
        cond = compile_expression('(variables.a == "x" or variables.b == "y") and variables.c')
        ctx = WorkflowContext(variables={"a": "x", "c": True})
        assert cond(ctx) is True
        ctx2 = WorkflowContext(variables={"b": "y", "c": False})
        assert cond(ctx2) is False

    def test_null_comparison(self):
        cond = compile_expression('variables.x == null')
        assert cond(WorkflowContext()) is True  # missing → None == None
        assert cond(WorkflowContext(variables={"x": "val"})) is False

    def test_not_null(self):
        cond = compile_expression('variables.x != null')
        assert cond(WorkflowContext(variables={"x": "val"})) is True
        assert cond(WorkflowContext()) is False

    def test_boolean_literals(self):
        cond = compile_expression('variables.flag == true')
        assert cond(WorkflowContext(variables={"flag": True})) is True
        assert cond(WorkflowContext(variables={"flag": False})) is False

        cond2 = compile_expression('variables.flag == false')
        assert cond2(WorkflowContext(variables={"flag": False})) is True

    def test_number_comparison(self):
        cond = compile_expression('variables.count == 5')
        assert cond(WorkflowContext(variables={"count": 5})) is True
        assert cond(WorkflowContext(variables={"count": 3})) is False

    def test_float_comparison(self):
        cond = compile_expression('variables.score == 3.14')
        assert cond(WorkflowContext(variables={"score": 3.14})) is True

    def test_hyphenated_dotpath(self):
        cond = compile_expression('results.risky-step.status == "success"')
        ctx = WorkflowContext()
        ctx.results["risky-step"] = StepResult(name="risky-step", status="success")
        assert cond(ctx) is True

    def test_missing_path_returns_none(self):
        cond = compile_expression('results.nonexistent.output == null')
        ctx = WorkflowContext()
        assert cond(ctx) is True

    def test_complex_combined(self):
        """Combined: coalesce + or + equality."""
        cond = compile_expression(
            'variables.mode ?? "default" == "thorough" or variables.force == true'
        )
        assert cond(WorkflowContext(variables={"mode": "thorough"})) is True
        assert cond(WorkflowContext(variables={"force": True})) is True
        assert cond(WorkflowContext()) is False  # default != thorough, force missing

    def test_syntax_error_invalid_char(self):
        with pytest.raises(SyntaxError):
            compile_expression('variables.x @ 5')

    def test_syntax_error_trailing_tokens(self):
        with pytest.raises(SyntaxError):
            compile_expression('variables.x == "y" "z"')

    def test_single_quoted_string(self):
        cond = compile_expression("variables.x == 'hello'")
        assert cond(WorkflowContext(variables={"x": "hello"})) is True


# ============ Tokenizer ============


class TestTokenizer:
    def test_basic_tokens(self):
        tokens = _tokenize('variables.x == "hello"')
        types = [t[0] for t in tokens]
        assert "IDENT" in types
        assert "DOT" in types
        assert "EQ" in types
        assert "STRING" in types
        assert types[-1] == "EOF"

    def test_keywords(self):
        tokens = _tokenize('true and false or not null in')
        types = [t[0] for t in tokens]
        assert "TRUE" in types
        assert "AND" in types
        assert "FALSE" in types
        assert "OR" in types
        assert "NOT" in types
        assert "NULL" in types
        assert "IN" in types

    def test_coalesce_and_neq(self):
        tokens = _tokenize('x ?? "d" != "e"')
        types = [t[0] for t in tokens]
        assert "COALESCE" in types
        assert "NEQ" in types

    def test_brackets_and_commas(self):
        tokens = _tokenize('x in ["a", "b"]')
        types = [t[0] for t in tokens]
        assert "LBRACKET" in types
        assert "RBRACKET" in types
        assert "COMMA" in types


# ============ Module Resolver ============


class TestModuleResolver:
    def test_load_modules(self):
        modules = _load_modules(FIXTURES_DIR)
        assert "conditions" in modules
        assert "schemas" in modules
        # workflow.py should be skipped
        assert "workflow" not in modules

    def test_resolve_condition_ref(self):
        modules = _load_modules(FIXTURES_DIR)
        fn = _resolve_ref("conditions.is_thorough", modules, "when_fn")
        assert callable(fn)
        ctx = WorkflowContext(variables={"mode": "thorough"})
        assert fn(ctx) is True

    def test_resolve_schema_ref(self):
        modules = _load_modules(FIXTURES_DIR)
        cls = _resolve_ref("schemas.SummaryOutput", modules, "output_schema")
        obj = cls(total_items=3, status="done")
        assert obj.total_items == 3

    def test_resolve_missing_module(self):
        modules = _load_modules(FIXTURES_DIR)
        with pytest.raises(ValueError, match="module 'nonexistent' not found"):
            _resolve_ref("nonexistent.foo", modules, "when_fn")

    def test_resolve_missing_attr(self):
        modules = _load_modules(FIXTURES_DIR)
        with pytest.raises(ValueError, match="'nonexistent' not found in 'conditions'"):
            _resolve_ref("conditions.nonexistent", modules, "when_fn")

    def test_resolve_bad_format(self):
        modules = _load_modules(FIXTURES_DIR)
        with pytest.raises(ValueError, match="expected 'module.name'"):
            _resolve_ref("noperiod", modules, "when_fn")


# ============ Block Compilation ============


class TestBlockCompilation:
    def _modules(self):
        return _load_modules(FIXTURES_DIR)

    def test_shell_inline_command(self):
        block = compile_block(
            {"shell": "echo-step", "command": "echo hello", "result_var": "out"},
            FIXTURES_DIR, self._modules(),
        )
        assert isinstance(block, ShellStep)
        assert block.name == "echo-step"
        assert block.command == "echo hello"
        assert block.result_var == "out"

    def test_shell_script(self):
        block = compile_block(
            {"shell": "script-step", "script": "scripts/check.sh", "args": "--flag",
             "env": {"KEY": "val"}},
            FIXTURES_DIR, self._modules(),
        )
        assert isinstance(block, ShellStep)
        assert block.script == "scripts/check.sh"
        assert block.args == "--flag"
        assert block.env == {"KEY": "val"}
        assert block.command == ""

    def test_shell_mutual_exclusion(self):
        with pytest.raises(ValueError, match="cannot specify both 'command' and 'script'"):
            compile_block(
                {"shell": "bad", "command": "echo", "script": "check.sh"},
                FIXTURES_DIR, self._modules(),
            )

    def test_prompt_block(self):
        block = compile_block(
            {"prompt": "ask", "prompt_type": "choice", "message": "Pick:",
             "options": ["a", "b"], "default": "a", "result_var": "answer", "strict": False},
            FIXTURES_DIR, self._modules(),
        )
        assert isinstance(block, PromptStep)
        assert block.prompt_type == "choice"
        assert block.options == ["a", "b"]
        assert block.strict is False

    def test_llm_with_prompt_file(self):
        block = compile_block(
            {"llm": "classify", "prompt": "classify.md", "model": "haiku",
             "tools": ["Read"], "output_schema": "schemas.SummaryOutput"},
            FIXTURES_DIR, self._modules(),
        )
        assert isinstance(block, LLMStep)
        assert block.prompt == "classify.md"
        assert block.model == "haiku"
        assert block.tools == ["Read"]
        assert block.output_schema is not None

    def test_llm_with_prompt_text(self):
        block = compile_block(
            {"llm": "inline", "prompt_text": "Analyze this."},
            FIXTURES_DIR, self._modules(),
        )
        assert isinstance(block, LLMStep)
        assert block.prompt_text == "Analyze this."
        assert block.prompt == ""

    def test_llm_mutual_exclusion(self):
        with pytest.raises(ValueError, match="cannot specify both 'prompt' and 'prompt_text'"):
            compile_block(
                {"llm": "bad", "prompt": "file.md", "prompt_text": "inline"},
                FIXTURES_DIR, self._modules(),
            )

    def test_group_block(self):
        block = compile_block(
            {"group": "my-group", "model": "sonnet", "isolation": "subagent",
             "blocks": [{"shell": "inner", "command": "echo"}]},
            FIXTURES_DIR, self._modules(),
        )
        assert isinstance(block, GroupBlock)
        assert block.model == "sonnet"
        assert block.isolation == "subagent"
        assert len(block.blocks) == 1

    def test_loop_block(self):
        block = compile_block(
            {"loop": "items", "over": "results.detect.structured_output.items",
             "as": "item", "blocks": [{"shell": "proc", "command": "echo"}]},
            FIXTURES_DIR, self._modules(),
        )
        assert isinstance(block, LoopBlock)
        assert block.loop_over == "results.detect.structured_output.items"
        assert block.loop_var == "item"

    def test_retry_with_inline_until(self):
        block = compile_block(
            {"retry": "r", "max_attempts": 5,
             "until": 'results.cmd.status == "success"',
             "blocks": [{"shell": "cmd", "command": "echo"}]},
            FIXTURES_DIR, self._modules(),
        )
        assert isinstance(block, RetryBlock)
        assert block.max_attempts == 5

    def test_retry_with_until_fn(self):
        block = compile_block(
            {"retry": "r", "until_fn": "conditions.flaky_succeeded",
             "blocks": [{"shell": "cmd", "command": "echo"}]},
            FIXTURES_DIR, self._modules(),
        )
        assert isinstance(block, RetryBlock)
        # Test the callable
        ctx = WorkflowContext()
        ctx.results["flaky-cmd"] = StepResult(name="flaky-cmd", status="success")
        assert block.until(ctx) is True

    def test_retry_missing_until(self):
        with pytest.raises(ValueError, match="must specify 'until' or 'until_fn'"):
            compile_block(
                {"retry": "r", "blocks": [{"shell": "cmd", "command": "echo"}]},
                FIXTURES_DIR, self._modules(),
            )

    def test_conditional_block(self):
        block = compile_block(
            {"conditional": "branch-step",
             "branches": [
                 {"when": 'variables.x == "a"',
                  "blocks": [{"shell": "a-path", "command": "echo a"}]},
                 {"when_fn": "conditions.is_thorough",
                  "blocks": [{"shell": "thorough", "command": "echo t"}]},
             ],
             "default": [{"shell": "fallback", "command": "echo default"}]},
            FIXTURES_DIR, self._modules(),
        )
        assert isinstance(block, ConditionalBlock)
        assert len(block.branches) == 2
        assert len(block.default) == 1

    def test_subworkflow_block(self):
        block = compile_block(
            {"subworkflow": "call-it", "workflow": "helper",
             "inject": {"key": "{{results.x.output}}"}},
            FIXTURES_DIR, self._modules(),
        )
        assert isinstance(block, SubWorkflow)
        assert block.workflow == "helper"
        assert block.inject == {"key": "{{results.x.output}}"}

    def test_parallel_block(self):
        block = compile_block(
            {"parallel": "checks", "for": "results.items",
             "as": "item", "max_concurrency": 4, "model": "sonnet",
             "template": [{"llm": "check", "prompt": "classify.md"}]},
            FIXTURES_DIR, self._modules(),
        )
        assert isinstance(block, ParallelEachBlock)
        assert block.parallel_for == "results.items"
        assert block.item_var == "item"
        assert block.max_concurrency == 4

    def test_blockbase_fields(self):
        block = compile_block(
            {"shell": "step", "command": "echo",
             "key": "custom-key", "isolation": "subagent",
             "context_hint": "some context"},
            FIXTURES_DIR, self._modules(),
        )
        assert block.key == "custom-key"
        assert block.isolation == "subagent"
        assert block.context_hint == "some context"

    def test_when_condition(self):
        block = compile_block(
            {"shell": "guarded", "command": "echo",
             "when": 'variables.enabled == true'},
            FIXTURES_DIR, self._modules(),
        )
        assert block.condition is not None
        ctx = WorkflowContext(variables={"enabled": True})
        assert block.condition(ctx) is True

    def test_when_fn_condition(self):
        block = compile_block(
            {"shell": "guarded", "command": "echo",
             "when_fn": "conditions.is_thorough"},
            FIXTURES_DIR, self._modules(),
        )
        assert block.condition is not None
        ctx = WorkflowContext(variables={"mode": "thorough"})
        assert block.condition(ctx) is True

    def test_when_and_when_fn_mutual_exclusion(self):
        with pytest.raises(ValueError, match="Cannot specify both"):
            compile_block(
                {"shell": "bad", "command": "echo",
                 "when": 'variables.x', "when_fn": "conditions.is_thorough"},
                FIXTURES_DIR, self._modules(),
            )

    def test_unknown_block_type(self):
        with pytest.raises(ValueError, match="Unknown block type"):
            compile_block(
                {"unknown_type": "step"},
                FIXTURES_DIR, self._modules(),
            )


# ============ Full Round-Trip: compile_workflow ============


class TestCompileWorkflow:
    def test_compile_fixture(self):
        wf = compile_workflow(FIXTURES_DIR)
        assert isinstance(wf, WorkflowDef)
        assert wf.name == "compiler-test"
        assert wf.description.startswith("Test workflow")
        assert wf.prompt_dir == str(FIXTURES_DIR / "prompts")
        assert wf.source_path == str(FIXTURES_DIR / "workflow.yaml")

    def test_all_block_types_present(self):
        wf = compile_workflow(FIXTURES_DIR)

        def _collect_types(blocks):
            types = set()
            for b in blocks:
                types.add(type(b).__name__)
                if hasattr(b, "blocks"):
                    types |= _collect_types(b.blocks)
                if hasattr(b, "branches"):
                    for branch in b.branches:
                        types |= _collect_types(branch.blocks)
                if hasattr(b, "default") and isinstance(b.default, list):
                    types |= _collect_types(b.default)
                if hasattr(b, "template"):
                    tmpl = getattr(b, "template")
                    if isinstance(tmpl, list):
                        types |= _collect_types(tmpl)
            return types

        all_types = _collect_types(wf.blocks)
        expected = {
            "ShellStep", "PromptStep", "LLMStep", "GroupBlock",
            "LoopBlock", "RetryBlock", "ConditionalBlock",
            "SubWorkflow", "ParallelEachBlock",
        }
        assert expected == all_types, f"Missing: {expected - all_types}, Extra: {all_types - expected}"

    def test_block_count(self):
        wf = compile_workflow(FIXTURES_DIR)
        assert len(wf.blocks) >= 10
        # Verify key named blocks exist
        block_names = {b.name for b in wf.blocks}
        assert "detect" in block_names
        assert "classify" in block_names

    def test_shell_with_env_and_script(self):
        wf = compile_workflow(FIXTURES_DIR)
        run_script = wf.blocks[1]
        assert isinstance(run_script, ShellStep)
        assert run_script.script == "scripts/check.sh"
        assert run_script.args == "--verbose"
        assert run_script.env == {"MY_VAR": "{{variables.project}}"}

    def test_llm_with_output_schema(self):
        wf = compile_workflow(FIXTURES_DIR)
        classify = wf.blocks[3]
        assert isinstance(classify, LLMStep)
        assert classify.output_schema is not None
        assert classify.isolation == "subagent"
        assert classify.context_hint == "project files"

    def test_llm_with_prompt_text(self):
        wf = compile_workflow(FIXTURES_DIR)
        inline = wf.blocks[4]
        assert isinstance(inline, LLMStep)
        assert inline.prompt_text.strip().startswith("Analyze")
        assert inline.prompt == ""

    def test_conditional_with_coalesce_when(self):
        wf = compile_workflow(FIXTURES_DIR)
        cond = wf.blocks[9]
        assert isinstance(cond, ConditionalBlock)
        # The outer when uses coalesce
        assert cond.condition is not None
        ctx = WorkflowContext()
        assert cond.condition(ctx) is True  # missing → "yes" == "yes"

    def test_custom_key(self):
        wf = compile_workflow(FIXTURES_DIR)
        keyed = wf.blocks[12]
        assert isinstance(keyed, ShellStep)
        assert keyed.key == "custom-{{variables.run_id}}"


# ============ Action Materialization (env/script/prompt_text) ============


class TestActionMaterialization:
    def test_shell_action_with_env(self):
        state = _make_state(project="myproject")
        step = ShellStep(
            name="test", command="echo hello",
            env={"MY_VAR": "{{variables.project}}"},
        )
        action = _build_shell_action(state, step, "test")
        assert action.env == {"MY_VAR": "myproject"}

    def test_shell_action_with_script_absolute_path(self):
        state = _make_state(workflow_dir="/wf/my-workflow")
        step = ShellStep(
            name="test", script="scripts/check.sh",
            args="--flag {{variables.mode}}",
        )
        action = _build_shell_action(state, step, "test")
        assert action.script_path == "/wf/my-workflow/scripts/check.sh"
        assert action.args is not None
        # No raw "script" attribute — only the resolved absolute script_path
        assert not hasattr(action, "script")

    def test_shell_action_script_without_workflow_dir(self):
        """When workflow_dir is absent, script_path falls back to the relative script."""
        state = _make_state()
        step = ShellStep(name="test", script="scripts/check.sh")
        action = _build_shell_action(state, step, "test")
        assert action.script_path == "scripts/check.sh"

    def test_shell_action_no_env_no_script(self):
        state = _make_state()
        step = ShellStep(name="test", command="echo hi")
        action = _build_shell_action(state, step, "test")
        assert action.env is None
        assert action.script_path is None

    def test_prompt_action_with_prompt_text(self):
        state = _make_state(item="widget")
        step = LLMStep(
            name="test", prompt_text="Analyze {{variables.item}}.",
        )
        action = _build_prompt_action(state, step, "test")
        assert action.prompt == "Analyze widget."
        assert "(inline)" in action.display

    def test_prompt_action_with_file(self, tmp_path):
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "test.md").write_text("# Test\nHello {{variables.name}}")
        state = _make_state(name="world")
        state.ctx.prompt_dir = str(prompt_dir)
        step = LLMStep(name="test", prompt="test.md")
        action = _build_prompt_action(state, step, "test")
        assert "Hello world" in action.prompt
        assert "test.md" in action.display


# ============ Script Path Resolution (end-to-end) ============


class TestScriptPathResolution:
    """Verify that script paths are resolved to absolute paths via workflow_dir."""

    def test_script_path_uses_workflow_dir_not_cwd(self):
        """script_path should resolve relative to workflow_dir, not cwd."""
        state = _make_state(cwd="/project", workflow_dir="/plugins/my-workflow")
        step = ShellStep(name="run-check", script="scripts/check.sh")
        action = _build_shell_action(state, step, "run-check")
        # Must be resolved relative to workflow_dir
        assert action.script_path == "/plugins/my-workflow/scripts/check.sh"
        # Must NOT be resolved relative to cwd
        assert not action.script_path.startswith("/project")

    def test_script_path_with_args_substitution(self):
        state = _make_state(workflow_dir="/wf", mode="fast")
        step = ShellStep(
            name="run", script="scripts/run.py",
            args="--mode {{variables.mode}} --verbose",
        )
        action = _build_shell_action(state, step, "run")
        assert action.script_path == "/wf/scripts/run.py"
        assert action.args == "--mode fast --verbose"


# ============ Dry-Run for Script-Based Shell Steps ============


class TestDryRunScriptShell:
    def test_dry_run_shell_with_script(self):
        state = _make_state(workflow_dir="/wf")
        step = ShellStep(
            name="check", script="scripts/check.sh",
            args="--flag", env={"KEY": "val"},
        )
        action = _build_dry_run_action(state, step, "check")
        assert action.dry_run is True
        assert action.script_path == "/wf/scripts/check.sh"
        assert action.args == "--flag"
        assert action.env == {"KEY": "val"}

    def test_dry_run_shell_with_command(self):
        state = _make_state()
        step = ShellStep(name="echo", command="echo hello")
        action = _build_dry_run_action(state, step, "echo")
        assert action.dry_run is True
        assert action.command == "echo hello"
        assert action.script_path is None


# ============ Compiler Robustness ============


class TestCompilerRobustness:
    def test_empty_yaml_file(self, tmp_path):
        """An empty YAML file should produce a clear error."""
        wf_dir = tmp_path / "empty-wf"
        wf_dir.mkdir()
        (wf_dir / "workflow.yaml").write_text("")
        with pytest.raises(ValueError, match="expected a YAML mapping"):
            compile_workflow(wf_dir)

    def test_yaml_list_top_level(self, tmp_path):
        """A YAML list at the top level should produce a clear error."""
        wf_dir = tmp_path / "list-wf"
        wf_dir.mkdir()
        (wf_dir / "workflow.yaml").write_text("- item1\n- item2\n")
        with pytest.raises(ValueError, match="expected a YAML mapping"):
            compile_workflow(wf_dir)

    def test_unknown_first_key(self):
        """A block dict whose first key isn't a recognized type should be rejected."""
        with pytest.raises(ValueError, match="Unknown block type"):
            compile_block(
                {"command": "echo", "shell": "step"},
                FIXTURES_DIR, _load_modules(FIXTURES_DIR),
            )

    def test_env_values_coerced_to_str(self):
        """Numeric/boolean YAML env values are coerced to str."""
        block = compile_block(
            {"shell": "step", "command": "echo",
             "env": {"PORT": 8080, "DEBUG": True}},
            FIXTURES_DIR, _load_modules(FIXTURES_DIR),
        )
        assert block.env == {"PORT": "8080", "DEBUG": "True"}


class TestHaltCompilation:
    """Test halt and halt_on_exhaustion compilation from YAML."""

    def test_halt_on_any_block(self):
        """halt field compiles on any block type."""
        block = compile_block(
            {"shell": "check", "command": "echo ok",
             "halt": "Check failed for {{variables.item}}"},
            FIXTURES_DIR, _load_modules(FIXTURES_DIR),
        )
        assert block.halt == "Check failed for {{variables.item}}"

    def test_halt_default_empty(self):
        """halt defaults to empty string when not specified."""
        block = compile_block(
            {"shell": "check", "command": "echo ok"},
            FIXTURES_DIR, _load_modules(FIXTURES_DIR),
        )
        assert block.halt == ""

    def test_halt_on_exhaustion_retry(self):
        """halt_on_exhaustion compiles on retry blocks."""
        block = compile_block(
            {"retry": "stabilize", "max_attempts": 3,
             "until": 'results.check.status == "success"',
             "halt_on_exhaustion": "Stabilization failed after 3 attempts",
             "blocks": [{"shell": "check", "command": "echo test"}]},
            FIXTURES_DIR, _load_modules(FIXTURES_DIR),
        )
        assert block.halt_on_exhaustion == "Stabilization failed after 3 attempts"

    def test_halt_on_exhaustion_default_empty(self):
        """halt_on_exhaustion defaults to empty string."""
        block = compile_block(
            {"retry": "stabilize", "max_attempts": 3,
             "until": 'results.check.status == "success"',
             "blocks": [{"shell": "check", "command": "echo test"}]},
            FIXTURES_DIR, _load_modules(FIXTURES_DIR),
        )
        assert block.halt_on_exhaustion == ""
