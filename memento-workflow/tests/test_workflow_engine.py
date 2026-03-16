"""Tests for workflow engine — types, loader, and engine-bundled workflows.

Tests for the state machine (advance/submit) are in test_workflow_state_machine.py.
Tests for the MCP tools are in test_workflow_mcp_tools.py.
Tests for memento's workflow definitions are in memento/tests/test_workflow_definitions.py.

NOTE: TestSubstitute, TestSubstituteWithFiles, and TestEvaluateCondition were
previously duplicated here and in test_workflow_state_machine.py. They now live
only in test_workflow_state_machine.py (closer to the state machine code).
"""

from pathlib import Path


from conftest import _types_ns, _state_ns, _compiler_ns, _loader_ns

# Engine-bundled skills (test-workflow lives here)
PLUGIN_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

# Types
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

# State
load_prompt = _state_ns["load_prompt"]
workflow_hash = _state_ns["workflow_hash"]

# Compiler / Loader
compile_workflow = _compiler_ns["compile_workflow"]
load_workflow = _loader_ns["load_workflow"]
discover_workflows = _loader_ns["discover_workflows"]


def _load_workflow_file(workflow_name: str) -> dict:
    """Load a workflow definition from engine-bundled skills directory."""
    workflow_dir = PLUGIN_SKILLS_DIR / workflow_name
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

    def test_get_var_dotted_results_key(self):
        """SubWorkflow result at 'develop.explore' resolves via longest-prefix match."""
        ctx = WorkflowContext()
        ctx.results["develop.explore"] = StepResult(
            name="explore",
            structured_output={"findings": [{"tag": "DECISION", "text": "use REST"}]},
        )
        val = ctx.get_var("results.develop.explore.structured_output.findings")
        assert isinstance(val, list)
        assert val[0]["tag"] == "DECISION"

    def test_get_var_simple_results_key_still_works(self):
        """Backward compat: simple key like 'classify' still resolves."""
        ctx = WorkflowContext()
        ctx.results["classify"] = StepResult(
            name="classify",
            structured_output={"scope": "backend"},
        )
        assert ctx.get_var("results.classify.structured_output.scope") == "backend"

    def test_get_var_dotted_key_prefers_longer_match(self):
        """When both 'develop' and 'develop.explore' exist, longer match wins."""
        ctx = WorkflowContext()
        ctx.results["develop"] = StepResult(
            name="develop",
            structured_output={"summary": "dev done"},
        )
        ctx.results["develop.explore"] = StepResult(
            name="explore",
            structured_output={"files": ["a.py"]},
        )
        # Should resolve to develop.explore, not develop
        assert ctx.get_var("results.develop.explore.structured_output.files") == ["a.py"]
        # develop still works for its own paths
        assert ctx.get_var("results.develop.structured_output.summary") == "dev done"

    def test_get_var_results_returns_structured_output(self):
        """{{results}} returns structured_output when available, not model_dump()."""
        ctx = WorkflowContext()
        ctx.results["scope"] = StepResult(
            name="scope", status="success",
            output="raw text that should not appear",
            structured_output={"files": ["a.py"], "competencies": ["python"]},
            exec_key="scope", duration=1.5, cost_usd=0.01, model="haiku",
        )
        result = ctx.get_var("results")
        # Should return structured_output directly, not model_dump
        assert result == {"scope": {"files": ["a.py"], "competencies": ["python"]}}
        # Only structured_output keys, no StepResult metadata
        assert set(result["scope"].keys()) == {"files", "competencies"}

    def test_get_var_results_falls_back_to_output(self):
        """{{results}} falls back to output when structured_output is None."""
        ctx = WorkflowContext()
        ctx.results["check"] = StepResult(
            name="check", status="success",
            output='{"exists": true}',
            structured_output=None,
        )
        result = ctx.get_var("results")
        assert result == {"check": '{"exists": true}'}

    def test_get_var_results_mixed_steps(self):
        """{{results}} handles mix of structured and plain output steps."""
        ctx = WorkflowContext()
        ctx.results["scope"] = StepResult(
            name="scope",
            structured_output={"files": ["a.py"]},
        )
        ctx.results["shell"] = StepResult(
            name="shell", output="plain text",
            structured_output=None,
        )
        ctx.results["reviews"] = StepResult(
            name="reviews",
            structured_output=[
                {"competency": "python", "findings": []},
                {"competency": "security", "findings": [{"severity": "CRITICAL"}]},
            ],
        )
        result = ctx.get_var("results")
        assert result["scope"] == {"files": ["a.py"]}
        assert result["shell"] == "plain text"
        assert len(result["reviews"]) == 2
        assert result["reviews"][0]["competency"] == "python"

    def test_get_var_results_dotpath_still_works(self):
        """Specific dotpath access (results.step.field) still works."""
        ctx = WorkflowContext()
        ctx.results["classify"] = StepResult(
            name="classify", status="success",
            output="raw output",
            structured_output={"scope": "backend"},
        )
        # Dotpath access still resolves against the StepResult object
        assert ctx.get_var("results.classify.structured_output.scope") == "backend"
        assert ctx.get_var("results.classify.output") == "raw output"
        assert ctx.get_var("results.classify.status") == "success"

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


# ============ Load Prompt ============


class TestLoadPrompt:
    def test_load_and_substitute(self, tmp_path):
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "classify.md").write_text(
            "# Classify\nTask: {{variables.task}}\nMode: {{variables.mode}}\n"
        )
        ctx = WorkflowContext(
            variables={"task": "add login", "mode": "protocol"},
            prompt_dir=str(prompt_dir),
        )
        text = load_prompt("classify.md", ctx)
        assert "# Classify" in text
        assert "Task: add login" in text
        assert "Mode: protocol" in text

    def test_load_with_results(self, tmp_path):
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "plan.md").write_text("Prior: {{results.classify.output}}")
        ctx = WorkflowContext(prompt_dir=str(prompt_dir))
        ctx.results["classify"] = StepResult(name="classify", output="backend only")
        text = load_prompt("plan.md", ctx)
        assert "Prior: backend only" in text


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


# ============ Test Workflow (engine-bundled) ============


class TestTestWorkflowDefinition:
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

    def test_test_workflow_summary_schema(self):
        ns = _load_workflow_file("test-workflow")
        schema = ns["SummaryOutput"].model_json_schema()
        assert "total_items" in schema["properties"]
        assert "status" in schema["properties"]
        assert "notes" in schema["properties"]
        obj = ns["SummaryOutput"](total_items=3, status="complete", notes="test")
        assert obj.total_items == 3

    def test_test_workflow_prompts_exist(self):
        """All test-workflow prompts should exist."""
        prompts = [
            "classify.md", "summarize.md",
            "session-step1.md", "session-step2.md",
            "parallel-check.md",
            "ask-single.md", "ask-group-step1.md",
            "ask-group-step2.md", "ask-parallel.md",
        ]
        for prompt in prompts:
            full = PLUGIN_SKILLS_DIR / "test-workflow" / "prompts" / prompt
            assert full.exists(), f"Missing prompt: test-workflow/prompts/{prompt}"

    def test_test_workflow_prompts_have_heading(self):
        """Every test-workflow prompt should start with a markdown heading."""
        for prompt_file in (PLUGIN_SKILLS_DIR / "test-workflow").rglob("prompts/*.md"):
            text = prompt_file.read_text(encoding="utf-8").strip()
            assert text, f"Prompt file is empty: {prompt_file}"
            assert text.startswith("#"), (
                f"Prompt missing heading: {prompt_file}"
            )


# ============ Workflow Hash ============


class TestWorkflowHash:
    def test_hash_with_source(self, tmp_path):
        (tmp_path / "workflow.py").write_text("# v1")
        wf = WorkflowDef(
            name="test", description="test",
            source_path=str(tmp_path / "workflow.py"),
        )
        h = workflow_hash(wf)
        assert len(h) == 64  # SHA256 hex

    def test_hash_no_source(self):
        wf = WorkflowDef(name="test", description="test")
        assert workflow_hash(wf) == ""

    def test_hash_changes_on_source_change(self, tmp_path):
        src = tmp_path / "workflow.py"
        src.write_text("# v1")
        wf = WorkflowDef(name="test", description="test", source_path=str(src))
        h1 = workflow_hash(wf)

        src.write_text("# v2")
        h2 = workflow_hash(wf)
        assert h1 != h2


# ============ Types: isolation field ============


class TestIsolationField:
    def test_default_is_inline(self):
        step = ShellStep(name="test", command="echo")
        assert step.isolation == "inline"

    def test_set_subagent(self):
        step = LLMStep(name="test", prompt="test.md", isolation="subagent")
        assert step.isolation == "subagent"

    def test_context_hint(self):
        step = LLMStep(name="test", prompt="test.md",
                       isolation="subagent", context_hint="project files")
        assert step.context_hint == "project files"

    def test_group_block_no_llm_session_policy(self):
        """GroupBlock should no longer have llm_session_policy."""
        g = GroupBlock(name="test", blocks=[])
        assert not hasattr(g, "llm_session_policy") or g.model_fields.get("llm_session_policy") is None

    def test_workflow_context_no_io_handler(self):
        """WorkflowContext should no longer have io_handler."""
        ctx = WorkflowContext()
        assert "io_handler" not in ctx.model_fields
