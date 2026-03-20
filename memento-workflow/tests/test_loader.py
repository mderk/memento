"""Tests for workflow loader, discovery, and engine-bundled workflow definitions."""

from pathlib import Path

from conftest import _types_ns, _state_ns, _loader_ns

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

# Loader
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
