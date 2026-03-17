"""Tests for memento workflow definitions, output schemas, and prompt files.

Validates that memento's deployed workflows (static/workflows/) and plugin-only
workflows (skills/) load correctly, have expected structure, and all prompts exist.

Engine types are loaded from the sibling memento-workflow plugin.

NOTE — Fragile exec() loading mechanism
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Engine modules (types.py, state.py, compiler.py, loader.py, etc.) are loaded
via exec() rather than normal imports because:
  1. The memento-workflow plugin uses relative imports internally, which fail
     when loaded from the memento test suite's different package context.
  2. _strip_relative_imports() removes those relative imports before exec().
  3. Symbols are manually threaded between namespaces (_types_ns → _state_ns
     → _compiler_ns → _loader_ns) to simulate the import chain.

This is inherently fragile: adding a new relative import, renaming a symbol, or
introducing a new transitive dependency can silently break the chain. If tests
begin failing with NameError or missing keys, check the exec() loading section
below — a new namespace or import may need to be added.
"""

import re
from pathlib import Path

from pydantic import BaseModel

# Engine scripts live in the sibling memento-workflow plugin
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "memento-workflow" / "scripts"

# Memento's workflow directories
MEMENTO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = MEMENTO_ROOT / "static" / "workflows"
MEMENTO_SKILLS_DIR = MEMENTO_ROOT / "skills"

# Engine-bundled workflows (test-workflow is in memento-workflow)
ENGINE_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "memento-workflow" / "skills"


def _strip_relative_imports(code: str) -> str:
    """Remove all 'from .xxx import (...)' and 'from .xxx import yyy' blocks."""
    code = re.sub(r"from \.+\w+ import \(.*?\)", "", code, flags=re.DOTALL)
    code = re.sub(r"from \.+\w+ import .+", "", code)
    return code


# Load types
_types_code = (SCRIPTS_DIR / "types.py").read_text()
_types_ns: dict = {"__name__": "types", "__annotations__": {}}
exec(compile(_types_code, str(SCRIPTS_DIR / "types.py"), "exec"), _types_ns)

WorkflowDef = _types_ns["WorkflowDef"]
WorkflowContext = _types_ns["WorkflowContext"]

# Load state modules (needed for loader)
_state_ns: dict = {
    "__name__": "state",
    "__annotations__": {},
    **{k: v for k, v in _types_ns.items() if not k.startswith("_")},
}
for _fname in ["protocol.py", "core.py", "utils.py", "actions.py", "checkpoint.py", "state.py"]:
    _code = _strip_relative_imports((SCRIPTS_DIR / _fname).read_text())
    exec(compile(_code, str(SCRIPTS_DIR / _fname), "exec"), _state_ns)

# Load compiler
_compiler_code = _strip_relative_imports((SCRIPTS_DIR / "compiler.py").read_text())
_compiler_ns: dict = {
    "__name__": "compiler",
    "__annotations__": {},
    "__builtins__": __builtins__,
    **{k: v for k, v in _types_ns.items() if not k.startswith("_")},
}
exec(compile(_compiler_code, str(SCRIPTS_DIR / "compiler.py"), "exec"), _compiler_ns)
compile_workflow = _compiler_ns["compile_workflow"]

# Load loader
_loader_code = _strip_relative_imports((SCRIPTS_DIR / "loader.py").read_text())
_loader_ns: dict = {
    "__name__": "loader",
    "__annotations__": {},
    "__builtins__": __builtins__,
    **{k: v for k, v in _types_ns.items() if not k.startswith("_")},
    "Path": Path,
    "compile_workflow": compile_workflow,
}
exec(compile(_loader_code, str(SCRIPTS_DIR / "loader.py"), "exec"), _loader_ns)

load_workflow = _loader_ns["load_workflow"]
discover_workflows = _loader_ns["discover_workflows"]


# ---------------------------------------------------------------------------
# Smoke test: verify exec() loading produced all expected symbols
# ---------------------------------------------------------------------------

def _check_namespace(ns: dict, expected: list[str], label: str) -> None:
    for sym in expected:
        assert sym in ns, f"exec() loading failed: '{sym}' missing from {label} namespace"


_check_namespace(_types_ns, ["WorkflowDef", "WorkflowContext", "LLMStep", "ShellStep",
                              "PromptStep", "GroupBlock", "LoopBlock", "RetryBlock",
                              "ConditionalBlock", "SubWorkflow", "ParallelEachBlock",
                              "Branch", "StepResult", "Block"], "_types_ns")
_check_namespace(_state_ns, ["advance", "apply_submit", "substitute",
                              "evaluate_condition", "RunState", "Frame"], "_state_ns")
_check_namespace(_compiler_ns, ["compile_workflow"], "_compiler_ns")
_check_namespace(_loader_ns, ["load_workflow", "discover_workflows"], "_loader_ns")


def _load_workflow_file(workflow_name: str) -> dict:
    """Load a workflow definition from memento's directories."""
    # Check memento skills first, then static workflows, then engine skills
    workflow_dir = MEMENTO_SKILLS_DIR / workflow_name
    if not workflow_dir.exists():
        workflow_dir = WORKFLOWS_DIR / workflow_name
    if not workflow_dir.exists():
        workflow_dir = ENGINE_SKILLS_DIR / workflow_name
    code = (workflow_dir / "workflow.py").read_text()
    ns = dict(_types_ns)
    ns["__name__"] = workflow_name
    exec(compile(code, str(workflow_dir / "workflow.py"), "exec"), ns)
    return ns


# ============ Loader (real workflow tests) ============


class TestLoaderRealWorkflows:
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
        wf = load_workflow(MEMENTO_SKILLS_DIR / "create-environment")
        assert wf.name == "create-environment"

    def test_discover_real_workflows(self):
        """discover_workflows finds 6 deployed workflows from static/workflows/."""
        registry = discover_workflows(WORKFLOWS_DIR)
        assert len(registry) == 6
        assert "development" in registry
        assert "code-review" in registry
        assert "testing" in registry
        assert "process-protocol" in registry
        assert "merge-protocol" in registry
        assert "verify-fix" in registry

    def test_discover_direct_workflow_dir(self):
        """discover_workflows loads workflow.py directly when path contains it."""
        registry = discover_workflows(MEMENTO_SKILLS_DIR / "create-environment")
        assert len(registry) == 1
        assert "create-environment" in registry

    def test_discover_with_plugin_skills(self):
        """discover_workflows finds all 8 workflows when both dirs are searched."""
        registry = discover_workflows(
            WORKFLOWS_DIR,
            MEMENTO_SKILLS_DIR / "create-environment",
            MEMENTO_SKILLS_DIR / "update-environment",
        )
        assert len(registry) == 8
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
        assert "classify" in block_names
        assert "explore" in block_names
        assert "plan" in block_names
        assert "implement" in block_names
        assert "protocol-implement" in block_names
        assert "fast-track" in block_names
        assert "acceptance-check" in block_names
        assert "acceptance-retry" in block_names
        assert "review" in block_names
        assert "complete" in block_names
        assert "protocol-complete" in block_names

    def test_code_review_has_parallel_block(self):
        ns = _load_workflow_file("code-review")
        cr = ns["WORKFLOW"]
        parallel_blocks = [b for b in cr.blocks if type(b).__name__ == "ParallelEachBlock"]
        assert len(parallel_blocks) == 1
        assert parallel_blocks[0].name == "reviews"


# ============ Output Schemas ============


class TestOutputSchemas:
    def test_develop_schemas(self):
        ns = _load_workflow_file("develop")
        schema = ns["ClassifyOutput"].model_json_schema()
        assert "scope" in schema["properties"]
        assert "fast_track" in schema["properties"]
        schema = ns["PlanOutput"].model_json_schema()
        assert "tasks" in schema["properties"]
        # New schemas
        assert "ExploreOutput" in ns
        assert "DevelopResult" in ns
        assert "Finding" in ns
        explore_schema = ns["ExploreOutput"].model_json_schema()
        assert "files_to_modify" in explore_schema["properties"]
        assert "findings" in explore_schema["properties"]
        result_schema = ns["DevelopResult"].model_json_schema()
        assert "files_changed" in result_schema["properties"]
        assert "findings" in result_schema["properties"]

    def test_acceptance_output_schema(self):
        ns = _load_workflow_file("develop")
        assert "AcceptanceOutput" in ns
        schema = ns["AcceptanceOutput"].model_json_schema()
        assert "requirements" in schema["properties"]
        assert "covered" in schema["properties"]
        assert "missing" in schema["properties"]
        assert "out_of_scope" in schema["properties"]
        assert "passed" in schema["properties"]
        # Validate instantiation
        obj = ns["AcceptanceOutput"](
            requirements=["r1"], covered=["r1"], missing=[], out_of_scope=[], passed=True
        )
        assert obj.passed is True

    def test_acceptance_tests_output_schema(self):
        ns = _load_workflow_file("develop")
        assert "AcceptanceTestsOutput" in ns
        schema = ns["AcceptanceTestsOutput"].model_json_schema()
        assert "test_files" in schema["properties"]
        obj = ns["AcceptanceTestsOutput"](test_files=["tests/test_foo.py"])
        assert obj.test_files == ["tests/test_foo.py"]

    def test_explore_has_output_schema(self):
        ns = _load_workflow_file("develop")
        explore = [b for b in ns["WORKFLOW"].blocks if b.name == "explore"][0]
        assert explore.output_schema is ns["ExploreOutput"]

    def test_plan_output_has_findings(self):
        ns = _load_workflow_file("develop")
        plan_schema = ns["PlanOutput"].model_json_schema()
        assert "findings" in plan_schema["properties"]

    def test_code_review_schemas(self):
        ns = _load_workflow_file("code-review")
        schema = ns["ReviewFindings"].model_json_schema()
        assert "findings" in schema["properties"]
        assert "has_blockers" in schema["properties"]
        assert "triage_table" in schema["properties"]
        obj = ns["ReviewFindings"](findings=[], has_blockers=False, verdict="APPROVE")
        assert obj.has_blockers is False
        assert obj.triage_table is None
        # ReviewFinding new fields
        finding_schema = ns["ReviewFinding"].model_json_schema()
        assert "pre_existing" in finding_schema["properties"]
        assert "verdict" in finding_schema["properties"]
        assert "rationale" in finding_schema["properties"]

    def test_testing_schemas(self):
        ns = _load_workflow_file("testing")
        schema = ns["TestResults"].model_json_schema()
        assert "passed" in schema["properties"]
        assert "failed" in schema["properties"]
        assert "coverage_details" in schema["properties"]
        obj = ns["TestResults"](passed=10, failed=0, errors=0)
        assert obj.coverage_pct is None
        assert obj.coverage_details == []
        # FileCoverage exists
        assert "FileCoverage" in ns
        # FailureDetail new fields
        failure_schema = ns["FailureDetail"].model_json_schema()
        assert "line" in failure_schema["properties"]
        assert "suggested_fix" in failure_schema["properties"]
        assert "priority" in failure_schema["properties"]

    def test_output_schema_references_model_class(self):
        """LLMStep.output_schema holds the model class, not a string path."""
        ns = _load_workflow_file("develop")
        classify_step = ns["WORKFLOW"].blocks[0]
        assert classify_step.output_schema is ns["ClassifyOutput"]
        assert issubclass(classify_step.output_schema, BaseModel)


# ============ Prompt Files ============


class TestPromptFiles:
    def test_all_memento_prompts_exist(self):
        # Deployed workflows (static/workflows/)
        deployed = {
            "develop": [
                "00-classify.md", "01-explore.md", "02-plan.md",
                "03a-write-tests.md", "03c-implement.md",
                "03e-fix.md", "03f-fix-verify-custom.md",
                "03g-acceptance-check.md", "03h-acceptance-tests.md",
                "03i-acceptance-impl.md",
                "04-fast-track.md", "05-complete.md",
            ],
            "code-review": [
                "01-scope.md", "02-review.md", "03-synthesize.md",
            ],
            "testing": [
                "01-analyze.md",
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
                "02-generate.md",
            ],
        }
        for workflow_name, prompts in plugin_only.items():
            for prompt in prompts:
                full = MEMENTO_SKILLS_DIR / workflow_name / "prompts" / prompt
                assert full.exists(), f"Missing prompt: {workflow_name}/prompts/{prompt}"

    def test_all_memento_prompts_have_heading(self):
        """Every memento prompt file should start with a markdown heading."""
        for workflow_dir in [WORKFLOWS_DIR, MEMENTO_SKILLS_DIR]:
            for prompt_file in workflow_dir.rglob("prompts/*.md"):
                text = prompt_file.read_text(encoding="utf-8").strip()
                if text:
                    assert text.startswith("#"), (
                        f"Prompt missing heading: {prompt_file.relative_to(workflow_dir.parent)}"
                    )


# ============ Structural Tests ============


class TestWorkflowStructure:
    def test_classify_is_top_level(self):
        """classify must be a top-level LLMStep, not inside a GroupBlock."""
        ns = _load_workflow_file("develop")
        first_block = ns["WORKFLOW"].blocks[0]
        assert type(first_block).__name__ == "LLMStep"
        assert first_block.name == "classify"

    def test_fast_track_placement(self):
        """fast-track appears after implement and before review in block order."""
        ns = _load_workflow_file("develop")
        block_names = [b.name for b in ns["WORKFLOW"].blocks]
        assert block_names.index("fast-track") > block_names.index("implement")
        assert block_names.index("fast-track") < block_names.index("review")

    def test_verify_red_has_refactor_condition(self):
        """verify-red step inside implement loop has a condition for refactors."""
        ns = _load_workflow_file("develop")
        implement_loop = [b for b in ns["WORKFLOW"].blocks if b.name == "implement"][0]
        verify_red = [b for b in implement_loop.blocks if b.name == "verify-red"][0]
        assert verify_red.condition is not None

    def test_process_protocol_single_loop(self):
        """process-protocol should have a single LoopBlock (no nested subtask loop)."""
        ns = _load_workflow_file("process-protocol")
        wf = ns["WORKFLOW"]
        loops = [b for b in wf.blocks if type(b).__name__ == "LoopBlock"]
        assert len(loops) == 1
        assert loops[0].name == "steps"
        # No nested LoopBlock inside the steps loop
        inner_loops = [b for b in loops[0].blocks if type(b).__name__ == "LoopBlock"]
        assert len(inner_loops) == 0

    def test_process_protocol_has_prepare_step(self):
        """process-protocol loop should have a prepare ShellStep."""
        ns = _load_workflow_file("process-protocol")
        wf = ns["WORKFLOW"]
        loop = [b for b in wf.blocks if type(b).__name__ == "LoopBlock"][0]
        prepare_steps = [b for b in loop.blocks if b.name == "prepare"]
        assert len(prepare_steps) == 1

    def test_protocol_implement_uses_variables_units(self):
        """protocol-implement loop iterates over variables.units."""
        ns = _load_workflow_file("develop")
        proto_loop = [b for b in ns["WORKFLOW"].blocks if b.name == "protocol-implement"][0]
        assert proto_loop.loop_over == "variables.units"
        assert proto_loop.loop_var == "unit"

    def test_explore_skipped_in_protocol(self):
        """explore condition returns False when mode=protocol."""
        ns = _load_workflow_file("develop")
        explore = [b for b in ns["WORKFLOW"].blocks if b.name == "explore"][0]
        # Build a minimal context mock
        ctx = type("Ctx", (), {
            "result_field": lambda self, name, field: False,
            "variables": {"mode": "protocol"},
        })()
        assert explore.condition(ctx) is False

    def test_plan_skipped_in_protocol(self):
        """plan condition returns False when mode=protocol."""
        ns = _load_workflow_file("develop")
        plan = [b for b in ns["WORKFLOW"].blocks if b.name == "plan"][0]
        ctx = type("Ctx", (), {
            "result_field": lambda self, name, field: False,
            "variables": {"mode": "protocol"},
        })()
        assert plan.condition(ctx) is False

    def test_acceptance_check_placement(self):
        """acceptance-check appears after verify-custom-retry and before review."""
        ns = _load_workflow_file("develop")
        block_names = [b.name for b in ns["WORKFLOW"].blocks]
        assert block_names.index("acceptance-check") > block_names.index("verify-custom-retry")
        assert block_names.index("acceptance-check") < block_names.index("review")

    def test_acceptance_check_skipped_for_fast_track(self):
        """acceptance-check condition returns False when fast_track is True."""
        ns = _load_workflow_file("develop")
        ac = [b for b in ns["WORKFLOW"].blocks if b.name == "acceptance-check"][0]
        ctx = type("Ctx", (), {
            "result_field": lambda self, name, field: True,
            "variables": {},
        })()
        assert ac.condition(ctx) is False

    def test_acceptance_check_runs_for_normal_tasks(self):
        """acceptance-check condition returns True when fast_track is False."""
        ns = _load_workflow_file("develop")
        ac = [b for b in ns["WORKFLOW"].blocks if b.name == "acceptance-check"][0]
        ctx = type("Ctx", (), {
            "result_field": lambda self, name, field: False,
            "variables": {},
        })()
        assert ac.condition(ctx) is True

    def test_acceptance_retry_has_correct_structure(self):
        """acceptance-retry block contains expected sub-blocks."""
        ns = _load_workflow_file("develop")
        retry = [b for b in ns["WORKFLOW"].blocks if b.name == "acceptance-retry"][0]
        sub_names = [b.name for b in retry.blocks]
        assert "write-acceptance-tests" in sub_names
        assert "verify-acceptance-red" in sub_names
        assert "implement-acceptance" in sub_names
        assert "verify-after-acceptance" in sub_names
        assert "acceptance-check" in sub_names

    def test_process_protocol_injects_verification_commands(self):
        """process-protocol passes verification_commands to development subworkflow."""
        ns = _load_workflow_file("process-protocol")
        wf = ns["WORKFLOW"]
        loop = [b for b in wf.blocks if type(b).__name__ == "LoopBlock"][0]
        develop = [b for b in loop.blocks if b.name == "develop"][0]
        assert "verification_commands" in develop.inject
        assert "units" in develop.inject


# ============ Prompt Contract Tests ============


class TestPromptContracts:
    """Verify key prompt phrases exist to prevent spec drift."""

    def test_analyze_prompt_has_coverage_enforcement(self):
        text = (WORKFLOWS_DIR / "testing/prompts/01-analyze.md").read_text()
        assert "coverage" in text.lower()
        assert "100%" in text or "gap" in text.lower()

    def test_analyze_prompt_has_priority(self):
        text = (WORKFLOWS_DIR / "testing/prompts/01-analyze.md").read_text()
        assert "CRITICAL" in text
        assert "REQUIRED" in text

    def test_synthesize_has_triage(self):
        text = (WORKFLOWS_DIR / "code-review/prompts/03-synthesize.md").read_text()
        assert "triage" in text.lower()
        assert "FIX" in text
        assert "DEFER" in text

    def test_review_has_pre_existing(self):
        text = (WORKFLOWS_DIR / "code-review/prompts/02-review.md").read_text()
        assert "pre_existing" in text or "pre-existing" in text.lower()

    def test_dev_tools_exists(self):
        """dev-tools.py must exist since ShellSteps reference it."""
        assert (WORKFLOWS_DIR / "develop" / "dev-tools.py").exists()

    def test_new_prompts_in_manifest(self):
        """New static prompt files must be listed in manifest.yaml."""
        manifest = (MEMENTO_ROOT / "static" / "manifest.yaml").read_text()
        assert "04-fast-track.md" in manifest
        assert "03g-acceptance-check.md" in manifest
        assert "03h-acceptance-tests.md" in manifest
        assert "03i-acceptance-impl.md" in manifest

    def test_manifest_includes_dev_tools(self):
        """dev-tools.py must be listed in manifest.yaml."""
        manifest = (MEMENTO_ROOT / "static" / "manifest.yaml").read_text()
        assert "workflows/develop/dev-tools.py" in manifest

    def test_manifest_includes_collect_result(self):
        """collect-result.py must be listed in manifest.yaml."""
        manifest = (MEMENTO_ROOT / "static" / "manifest.yaml").read_text()
        assert "workflows/develop/collect-result.py" in manifest

    def test_develop_prompts_do_not_repeat_task(self):
        """Only classify, explore (subagent), and fast-track prompts include {{variables.task}}.

        Explore is a subagent — its prompt is the ONLY context it receives,
        so it must include the task. Inline steps (plan, write-tests, implement)
        have the task from earlier in the conversation.
        """
        allowed = {"00-classify.md", "00r-resume-context.md", "01-explore.md", "04-fast-track.md"}
        prompts_dir = WORKFLOWS_DIR / "develop" / "prompts"
        for prompt_file in prompts_dir.glob("*.md"):
            text = prompt_file.read_text(encoding="utf-8")
            if prompt_file.name not in allowed:
                assert "{{variables.task}}" not in text, (
                    f"{prompt_file.name} should not contain {{{{variables.task}}}}"
                )


# ============ Script Path Tests ============


class TestScriptPaths:
    """Verify that ShellStep commands reference scripts that actually exist."""

    def _extract_script_paths(self, workflow_name: str) -> list[tuple[str, str]]:
        """Extract (step_name, script_path) from all ShellSteps in a workflow."""

        search_dir = MEMENTO_SKILLS_DIR / workflow_name
        if not search_dir.exists():
            search_dir = WORKFLOWS_DIR / workflow_name
        code = (search_dir / "workflow.py").read_text()

        results = []
        # Match python3 invocations with plugin_root-relative paths
        import re
        for match in re.finditer(
            r"python3\s+\{\{variables\.plugin_root\}\}/([^\s\"']+)", code
        ):
            script_rel = match.group(1)
            results.append(script_rel)
        return results

    def test_create_environment_script_paths(self):
        """All scripts referenced in create-environment workflow exist."""
        paths = self._extract_script_paths("create-environment")
        assert len(paths) > 0, "Should find script references"
        for rel_path in paths:
            full = MEMENTO_ROOT / rel_path
            assert full.exists(), f"Script not found: {rel_path}"

    def test_update_environment_script_paths(self):
        """All scripts referenced in update-environment workflow exist."""
        paths = self._extract_script_paths("update-environment")
        assert len(paths) > 0, "Should find script references"
        for rel_path in paths:
            full = MEMENTO_ROOT / rel_path
            assert full.exists(), f"Script not found: {rel_path}"
