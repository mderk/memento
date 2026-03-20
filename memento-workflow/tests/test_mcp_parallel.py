"""Integration tests for parallel child runs, auto-advance, and thread safety.

Tests parallel lane relay, structured output merging, parallel resume,
shell-only lane auto-advance, results in downstream prompts, and _runs_lock
thread safety.
"""

import json
from pathlib import Path

import pytest

from conftest import _types_ns, create_runner_ns

# Runner (fresh namespace — tests mutate globals)
_runner_ns = create_runner_ns()

# Extract tool functions
_start = _runner_ns["start"]
_submit = _runner_ns["submit"]
_next = _runner_ns["next"]
_cancel = _runner_ns["cancel"]
_list_workflows = _runner_ns["list_workflows"]
_status = _runner_ns["status"]
_runs = _runner_ns["_runs"]

# Types
ShellStep = _types_ns["ShellStep"]
GroupBlock = _types_ns["GroupBlock"]
LoopBlock = _types_ns["LoopBlock"]
PromptStep = _types_ns["PromptStep"]
LLMStep = _types_ns["LLMStep"]
ParallelEachBlock = _types_ns["ParallelEachBlock"]
WorkflowDef = _types_ns["WorkflowDef"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_runs():
    """Clear in-memory runs between tests."""
    _runs.clear()
    yield
    _runs.clear()


# ---------------------------------------------------------------------------
# Shared workflow factories
# ---------------------------------------------------------------------------


def _make_parallel_workflow(
    tmp_path,
    *,
    name="par-test",
    items_expr='["x", "y"]',
    with_trailing_shell=True,
):
    """Create a workflow dir with a ParallelEachBlock.

    Args:
        name: Workflow/directory name.
        items_expr: JSON expression for setup shell output items.
        with_trailing_shell: If True, adds a ShellStep after the parallel block.
    """
    wf_dir = tmp_path / name
    wf_dir.mkdir()
    prompts_dir = wf_dir / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "check.md").write_text("Check item: {{variables.par_item}}")

    trailing = (
        '        ShellStep(name="done", command="echo finished"),\n'
        if with_trailing_shell
        else ""
    )
    (wf_dir / "workflow.py").write_text(f"""
WORKFLOW = WorkflowDef(
    name="{name}",
    description="Parallel test",
    blocks=[
        ShellStep(
            name="setup",
            command='echo \\'{{\"items\": {items_expr}}}\\'',
            result_var="data",
        ),
        ParallelEachBlock(
            name="checks",
            template=[
                LLMStep(name="check", prompt="check.md", model="haiku"),
            ],
            parallel_for="variables.data.items",
        ),
{trailing}    ],
)
""")
    return tmp_path


def _make_parallel_shell_only_workflow(
    tmp_path,
    *,
    name="par-shell",
    items_expr='["a", "b", "c"]',
    with_trailing_shell=True,
):
    """Create a parallel workflow where lanes contain only shell steps (no LLM).

    Args:
        name: Workflow/directory name.
        items_expr: JSON expression for setup shell output items.
        with_trailing_shell: If True, adds a ShellStep after the parallel block.
    """
    wf_dir = tmp_path / name
    wf_dir.mkdir()

    trailing = (
        '        ShellStep(name="done", command="echo finished"),\n'
        if with_trailing_shell
        else ""
    )
    (wf_dir / "workflow.py").write_text(f"""
WORKFLOW = WorkflowDef(
    name="{name}",
    description="Parallel shell-only test",
    blocks=[
        ShellStep(
            name="setup",
            command='echo \\'{{\"items\": {items_expr}}}\\'',
            result_var="data",
        ),
        ParallelEachBlock(
            name="checks",
            item_var="par_item",
            template=[
                ShellStep(name="process", command="echo \\'{{{{variables.par_item}}}}\\'"),
            ],
            parallel_for="variables.data.items",
        ),
{trailing}    ],
)
""")
    return tmp_path


# ---------------------------------------------------------------------------
# Tests: Parallel child runs
# ---------------------------------------------------------------------------


class TestParallelChildRuns:
    @pytest.fixture
    def parallel_workflow(self, tmp_path):
        return _make_parallel_workflow(tmp_path)

    def test_parallel_emits_lanes(self, parallel_workflow):
        """Shell auto-advances, then parallel action with per-lane child_run_ids."""
        start_result = json.loads(
            _start(
                workflow="par-test",
                cwd=str(parallel_workflow),
                workflow_dirs=[str(parallel_workflow)],
            )
        )
        # "setup" shell was auto-advanced -> parallel action
        assert start_result["action"] == "parallel"
        assert "_shell_log" in start_result
        assert start_result["_shell_log"][0]["exec_key"] == "setup"
        assert len(start_result["lanes"]) == 2
        for lane in start_result["lanes"]:
            assert "child_run_id" in lane
            assert lane["relay"] is True

    def test_parallel_lane_relay(self, parallel_workflow):
        """Each parallel lane driven independently, parent completes after all lanes."""
        start_result = json.loads(
            _start(
                workflow="par-test",
                cwd=str(parallel_workflow),
                workflow_dirs=[str(parallel_workflow)],
            )
        )
        run_id = start_result["run_id"]
        parallel_exec_key = start_result["exec_key"]
        lanes = start_result["lanes"]

        # Drive each lane
        lane_summaries = []
        for lane in lanes:
            child_run_id = lane["child_run_id"]
            child_action = json.loads(_next(run_id=child_run_id))
            assert child_action["action"] == "prompt"

            child_result = json.loads(
                _submit(
                    run_id=child_run_id,
                    exec_key=child_action["exec_key"],
                    output=f"checked {child_run_id}",
                )
            )
            assert child_result["action"] == "completed"
            lane_summaries.append(f"lane done: {child_run_id}")

        # Submit parent -> "done" shell auto-advances -> completed
        result = json.loads(
            _submit(
                run_id=run_id,
                exec_key=parallel_exec_key,
                output=json.dumps(lane_summaries),
            )
        )
        assert result["action"] == "completed"
        assert "_shell_log" in result
        assert result["_shell_log"][0]["exec_key"] == "done"

    def test_parallel_auto_merges_structured_output(self, parallel_workflow):
        """Parallel submit auto-merges structured_output from child lanes."""
        start_result = json.loads(
            _start(
                workflow="par-test",
                cwd=str(parallel_workflow),
                workflow_dirs=[str(parallel_workflow)],
            )
        )
        run_id = start_result["run_id"]
        parallel_exec_key = start_result["exec_key"]
        lanes = start_result["lanes"]

        # Drive each lane with structured output
        for i, lane in enumerate(lanes):
            child_run_id = lane["child_run_id"]
            child_action = json.loads(_next(run_id=child_run_id))
            child_result = json.loads(
                _submit(
                    run_id=child_run_id,
                    exec_key=child_action["exec_key"],
                    output=f"checked item {i}",
                    structured_output={"item_index": i, "findings": [f"finding-{i}"]},
                )
            )
            assert child_result["action"] == "completed"

        # Submit parent -- engine should auto-merge child structured outputs
        result = json.loads(
            _submit(
                run_id=run_id,
                exec_key=parallel_exec_key,
                output="all lanes done",
            )
        )
        assert result["action"] == "completed"

        # Verify the parent's result has merged structured_output
        state = _runs[run_id]
        checks_result = state.ctx.results.get("checks")
        assert checks_result is not None
        assert isinstance(checks_result.structured_output, list)
        assert len(checks_result.structured_output) == 2
        # Verify all lane data is present
        indices = {item["item_index"] for item in checks_result.structured_output}
        assert indices == {0, 1}

    def test_parallel_auto_merge_fallback_to_output(self, parallel_workflow):
        """Parallel merge falls back to output when structured_output is None."""
        start_result = json.loads(
            _start(
                workflow="par-test",
                cwd=str(parallel_workflow),
                workflow_dirs=[str(parallel_workflow)],
            )
        )
        run_id = start_result["run_id"]
        parallel_exec_key = start_result["exec_key"]
        lanes = start_result["lanes"]

        # Drive each lane with only text output (no structured_output)
        for i, lane in enumerate(lanes):
            child_run_id = lane["child_run_id"]
            child_action = json.loads(_next(run_id=child_run_id))
            child_result = json.loads(
                _submit(
                    run_id=child_run_id,
                    exec_key=child_action["exec_key"],
                    output=f"result for item {i}",
                )
            )
            assert child_result["action"] == "completed"

        result = json.loads(
            _submit(
                run_id=run_id,
                exec_key=parallel_exec_key,
                output="done",
            )
        )
        assert result["action"] == "completed"

        state = _runs[run_id]
        checks_result = state.ctx.results.get("checks")
        assert checks_result is not None
        assert isinstance(checks_result.structured_output, list)
        assert len(checks_result.structured_output) == 2
        # Falls back to output strings with actual content
        assert set(checks_result.structured_output) == {
            "result for item 0",
            "result for item 1",
        }

    def test_parallel_merge_with_no_structured_output(self, parallel_workflow):
        """Lanes producing neither structured_output nor output yield None merge."""
        start_result = json.loads(
            _start(
                workflow="par-test",
                cwd=str(parallel_workflow),
                workflow_dirs=[str(parallel_workflow)],
            )
        )
        run_id = start_result["run_id"]
        parallel_exec_key = start_result["exec_key"]
        lanes = start_result["lanes"]

        # Drive lanes with empty output
        for lane in lanes:
            child_run_id = lane["child_run_id"]
            child_action = json.loads(_next(run_id=child_run_id))
            json.loads(
                _submit(
                    run_id=child_run_id,
                    exec_key=child_action["exec_key"],
                    output="",
                )
            )

        result = json.loads(
            _submit(
                run_id=run_id,
                exec_key=parallel_exec_key,
                output="done",
            )
        )
        assert result["action"] == "completed"

        state = _runs[run_id]
        checks_result = state.ctx.results.get("checks")
        assert checks_result is not None
        # Empty outputs still collected (empty string is truthy-ish but falsy -- should not appear)
        # _collect_parallel_results skips when both structured_output is None and output is falsy
        assert checks_result.structured_output is None

    def test_parallel_merge_mixed_structured_and_text(self, parallel_workflow):
        """Lanes with mix of structured_output and plain text are both collected."""
        start_result = json.loads(
            _start(
                workflow="par-test",
                cwd=str(parallel_workflow),
                workflow_dirs=[str(parallel_workflow)],
            )
        )
        run_id = start_result["run_id"]
        parallel_exec_key = start_result["exec_key"]
        lanes = start_result["lanes"]

        # Lane 0: structured output
        child0 = lanes[0]["child_run_id"]
        action0 = json.loads(_next(run_id=child0))
        json.loads(
            _submit(
                run_id=child0,
                exec_key=action0["exec_key"],
                output="text fallback",
                structured_output={"type": "structured", "score": 42},
            )
        )

        # Lane 1: text only
        child1 = lanes[1]["child_run_id"]
        action1 = json.loads(_next(run_id=child1))
        json.loads(
            _submit(
                run_id=child1,
                exec_key=action1["exec_key"],
                output="plain text result",
            )
        )

        result = json.loads(
            _submit(
                run_id=run_id,
                exec_key=parallel_exec_key,
                output="done",
            )
        )
        assert result["action"] == "completed"

        state = _runs[run_id]
        checks_result = state.ctx.results.get("checks")
        merged = checks_result.structured_output
        assert isinstance(merged, list)
        assert len(merged) == 2
        # One structured, one text fallback
        structured_items = [m for m in merged if isinstance(m, dict)]
        text_items = [m for m in merged if isinstance(m, str)]
        assert len(structured_items) == 1
        assert structured_items[0]["score"] == 42
        assert len(text_items) == 1
        assert text_items[0] == "plain text result"

    def test_cancel_cleans_child_runs(self, parallel_workflow):
        """Cancel cleans up both parent and child runs."""
        start_result = json.loads(
            _start(
                workflow="par-test",
                cwd=str(parallel_workflow),
                workflow_dirs=[str(parallel_workflow)],
            )
        )
        run_id = start_result["run_id"]
        child_ids = [lane["child_run_id"] for lane in start_result["lanes"]]

        # All runs should exist
        assert run_id in _runs
        for cid in child_ids:
            assert cid in _runs

        # Cancel parent
        cancel_result = json.loads(_cancel(run_id=run_id))
        assert cancel_result["action"] == "cancelled"

        # All should be cleaned up
        assert run_id not in _runs
        for cid in child_ids:
            assert cid not in _runs


# ---------------------------------------------------------------------------
# Tests: Parallel results available in downstream prompts
# ---------------------------------------------------------------------------


class TestParallelResultsInPrompts:
    """Verify that {{results}} in a step after ParallelEachBlock contains merged lane data."""

    @pytest.fixture
    def parallel_synthesize_workflow(self, tmp_path):
        wf_dir = tmp_path / "par-synth"
        wf_dir.mkdir()
        prompts_dir = wf_dir / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "review.md").write_text("Review item: {{variables.par_item}}")
        # Synthesize prompt uses {{results}} -- should contain merged parallel data
        (prompts_dir / "synthesize.md").write_text("All results:\n{{results}}")
        (wf_dir / "workflow.py").write_text(r"""
WORKFLOW = WorkflowDef(
    name="par-synth",
    description="Parallel + synthesize",
    blocks=[
        ShellStep(
            name="setup",
            command='echo \'{"items": ["alpha", "beta"]}\'',
            result_var="data",
        ),
        ParallelEachBlock(
            name="reviews",
            template=[
                LLMStep(name="review", prompt="review.md"),
            ],
            parallel_for="variables.data.items",
        ),
        LLMStep(name="synthesize", prompt="synthesize.md"),
    ],
)
""")
        return tmp_path

    def test_synthesize_prompt_contains_parallel_structured_data(
        self, parallel_synthesize_workflow
    ):
        """Synthesize step prompt contains structured data from all parallel lanes."""
        start_result = json.loads(
            _start(
                workflow="par-synth",
                cwd=str(parallel_synthesize_workflow),
                workflow_dirs=[str(parallel_synthesize_workflow)],
            )
        )
        run_id = start_result["run_id"]
        parallel_exec_key = start_result["exec_key"]
        lanes = start_result["lanes"]

        # Drive each lane with structured output
        for i, lane in enumerate(lanes):
            child_run_id = lane["child_run_id"]
            child_action = json.loads(_next(run_id=child_run_id))
            json.loads(
                _submit(
                    run_id=child_run_id,
                    exec_key=child_action["exec_key"],
                    output=f"reviewed item {i}",
                    structured_output={"item": i, "score": 90 + i},
                )
            )

        # Submit parallel -> should get synthesize prompt action
        synth_action = json.loads(
            _submit(
                run_id=run_id,
                exec_key=parallel_exec_key,
                output="all lanes done",
            )
        )
        assert synth_action["action"] == "prompt"

        # The synthesize prompt should contain the merged parallel data
        prompt_text = Path(synth_action["prompt_file"]).read_text()
        assert '"item"' in prompt_text
        assert '"score"' in prompt_text
        # Should contain data from BOTH lanes
        assert "90" in prompt_text
        assert "91" in prompt_text
        # Should NOT contain StepResult metadata
        assert "exec_key" not in prompt_text
        assert "cost_usd" not in prompt_text
        assert "duration" not in prompt_text

    def test_synthesize_prompt_no_raw_output_noise(self, parallel_synthesize_workflow):
        """{{results}} does not include raw output text when structured_output exists."""
        start_result = json.loads(
            _start(
                workflow="par-synth",
                cwd=str(parallel_synthesize_workflow),
                workflow_dirs=[str(parallel_synthesize_workflow)],
            )
        )
        run_id = start_result["run_id"]
        parallel_exec_key = start_result["exec_key"]
        lanes = start_result["lanes"]

        for i, lane in enumerate(lanes):
            child_run_id = lane["child_run_id"]
            child_action = json.loads(_next(run_id=child_run_id))
            json.loads(
                _submit(
                    run_id=child_run_id,
                    exec_key=child_action["exec_key"],
                    output="this raw text should NOT appear in synthesize prompt",
                    structured_output={"clean_data": True},
                )
            )

        synth_action = json.loads(
            _submit(
                run_id=run_id,
                exec_key=parallel_exec_key,
                output="done",
            )
        )
        assert synth_action["action"] == "prompt"
        prompt_text = Path(synth_action["prompt_file"]).read_text()
        # Raw output from lanes should not appear
        assert "this raw text should NOT appear" not in prompt_text
        # Structured data should appear (inline -- small enough)
        assert "clean_data" in prompt_text

    def test_large_results_externalized_to_context_files(
        self, parallel_synthesize_workflow
    ):
        """Large {{results}} data is written to context_files instead of inline."""
        start_result = json.loads(
            _start(
                workflow="par-synth",
                cwd=str(parallel_synthesize_workflow),
                workflow_dirs=[str(parallel_synthesize_workflow)],
            )
        )
        run_id = start_result["run_id"]
        parallel_exec_key = start_result["exec_key"]
        lanes = start_result["lanes"]

        # Submit large structured outputs to exceed externalization threshold
        for i, lane in enumerate(lanes):
            child_run_id = lane["child_run_id"]
            child_action = json.loads(_next(run_id=child_run_id))
            json.loads(
                _submit(
                    run_id=child_run_id,
                    exec_key=child_action["exec_key"],
                    output=f"reviewed {i}",
                    structured_output={
                        "competency": f"comp-{i}",
                        "findings": [
                            {
                                "description": f"finding {j} " + "x" * 200,
                                "severity": "SUGGESTION",
                            }
                            for j in range(5)
                        ],
                    },
                )
            )

        synth_action = json.loads(
            _submit(
                run_id=run_id,
                exec_key=parallel_exec_key,
                output="done",
            )
        )
        assert synth_action["action"] == "prompt"

        # Large data should be externalized to context_files
        assert synth_action.get("context_files") is not None
        assert len(synth_action["context_files"]) >= 1

        # Prompt text should NOT contain the large inline data
        prompt_text = Path(synth_action["prompt_file"]).read_text()
        assert "x" * 200 not in prompt_text
        assert "externalized" in prompt_text

        # Context file should contain the actual data
        data = json.loads(Path(synth_action["context_files"][0]).read_text())
        assert isinstance(data, dict)

    def test_file_based_submit_reads_result_from_disk(
        self, parallel_synthesize_workflow
    ):
        """When relay writes result to result_dir and submits without inline data, engine reads from file."""
        start_result = json.loads(
            _start(
                workflow="par-synth",
                cwd=str(parallel_synthesize_workflow),
                workflow_dirs=[str(parallel_synthesize_workflow)],
            )
        )
        run_id = start_result["run_id"]
        parallel_exec_key = start_result["exec_key"]
        lanes = start_result["lanes"]

        for i, lane in enumerate(lanes):
            child_run_id = lane["child_run_id"]
            child_action = json.loads(_next(run_id=child_run_id))
            json.loads(
                _submit(
                    run_id=child_run_id,
                    exec_key=child_action["exec_key"],
                    output=f"reviewed {i}",
                    structured_output={"item": i, "ok": True},
                )
            )

        synth_action = json.loads(
            _submit(
                run_id=run_id,
                exec_key=parallel_exec_key,
                output="done",
            )
        )
        assert synth_action["action"] == "prompt"
        synth_exec_key = synth_action["exec_key"]
        result_dir = synth_action.get("result_dir")
        assert result_dir is not None

        # Write result to result_dir (as relay would do)
        result_data = {"verdict": "APPROVE", "findings": []}
        Path(result_dir).mkdir(parents=True, exist_ok=True)
        (Path(result_dir) / "result.json").write_text(
            json.dumps(result_data), encoding="utf-8"
        )

        # Submit WITHOUT output or structured_output -- engine reads from file
        completed = json.loads(
            _submit(
                run_id=run_id,
                exec_key=synth_exec_key,
                status="success",
            )
        )
        assert completed["action"] == "completed"

        # Verify the result was read from file
        state = _runs[run_id]
        synth_result = state.ctx.results.get("synthesize")
        assert synth_result is not None
        assert synth_result.structured_output == result_data


# ---------------------------------------------------------------------------
# Tests: Parallel child resume from checkpoint
# ---------------------------------------------------------------------------


class TestParallelChildResume:
    """Test resume of parallel workflows with child runs persisted to disk."""

    @pytest.fixture
    def parallel_prompt_workflow(self, tmp_path):
        """Parallel workflow with LLM steps (requires relay, not auto-advanced)."""
        wf_dir = tmp_path / "par-resume"
        wf_dir.mkdir()
        prompts_dir = wf_dir / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "check.md").write_text("Check item: {{variables.par_item}}")
        (wf_dir / "workflow.py").write_text(r"""
WORKFLOW = WorkflowDef(
    name="par-resume",
    description="Parallel resume test",
    blocks=[
        ShellStep(
            name="setup",
            command='echo \'{"items": ["x", "y"]}\'',
            result_var="data",
        ),
        ParallelEachBlock(
            name="checks",
            template=[
                LLMStep(name="check", prompt="check.md", model="haiku"),
            ],
            parallel_for="variables.data.items",
        ),
        ShellStep(name="done", command="echo finished"),
    ],
)
""")
        return tmp_path

    def test_child_checkpoints_created(self, parallel_prompt_workflow):
        """Starting a parallel workflow creates checkpoint files for children."""
        start_result = json.loads(
            _start(
                workflow="par-resume",
                cwd=str(parallel_prompt_workflow),
                workflow_dirs=[str(parallel_prompt_workflow)],
            )
        )
        run_id = start_result["run_id"]
        assert start_result["action"] == "parallel"

        # Child checkpoint dirs should exist
        children_dir = (
            parallel_prompt_workflow / ".workflow-state" / run_id / "children"
        )
        assert children_dir.exists()
        child_dirs = list(children_dir.iterdir())
        assert len(child_dirs) == 2
        for cd in child_dirs:
            assert (cd / "state.json").exists()

    def test_resume_parallel_all_children_completed(self, parallel_prompt_workflow):
        """Resume after all children completed fast-forwards past parallel block."""
        start_result = json.loads(
            _start(
                workflow="par-resume",
                cwd=str(parallel_prompt_workflow),
                workflow_dirs=[str(parallel_prompt_workflow)],
            )
        )
        run_id = start_result["run_id"]
        parallel_exec_key = start_result["exec_key"]
        lanes = start_result["lanes"]

        # Drive all lanes to completion
        for lane in lanes:
            child_run_id = lane["child_run_id"]
            child_action = json.loads(_next(run_id=child_run_id))
            assert child_action["action"] == "prompt"
            child_result = json.loads(
                _submit(
                    run_id=child_run_id,
                    exec_key=child_action["exec_key"],
                    output=f"checked {child_run_id}",
                )
            )
            assert child_result["action"] == "completed"

        # Submit parent parallel
        result = json.loads(
            _submit(
                run_id=run_id,
                exec_key=parallel_exec_key,
                output="all lanes done",
            )
        )
        assert result["action"] == "completed"

        # Clear in-memory state (simulate server restart)
        _runs.clear()

        # Resume completed run -- falls back to fresh start
        result = json.loads(
            _start(
                workflow="par-resume",
                cwd=str(parallel_prompt_workflow),
                workflow_dirs=[str(parallel_prompt_workflow)],
                resume=run_id,
            )
        )
        assert result["run_id"] != run_id
        assert result["action"] == "parallel"  # fresh run hits parallel block

    def test_resume_parallel_children_in_progress(self, parallel_prompt_workflow):
        """Resume with in-progress children returns parallel action with resumed lanes."""
        start_result = json.loads(
            _start(
                workflow="par-resume",
                cwd=str(parallel_prompt_workflow),
                workflow_dirs=[str(parallel_prompt_workflow)],
            )
        )
        run_id = start_result["run_id"]
        lanes = start_result["lanes"]

        # Complete first lane only
        first_child_id = lanes[0]["child_run_id"]
        child_action = json.loads(_next(run_id=first_child_id))
        json.loads(
            _submit(
                run_id=first_child_id,
                exec_key=child_action["exec_key"],
                output="checked first",
            )
        )

        # Leave second lane in-progress (not submitted to)
        # Its checkpoint exists from _action_response auto-advance

        # Clear in-memory state (simulate server restart)
        _runs.clear()

        # Resume -- should return parallel action with resumed children
        result = json.loads(
            _start(
                workflow="par-resume",
                cwd=str(parallel_prompt_workflow),
                workflow_dirs=[str(parallel_prompt_workflow)],
                resume=run_id,
            )
        )
        assert result["action"] == "parallel"
        assert len(result["lanes"]) == 2

        # Children should be in _runs
        for lane in result["lanes"]:
            assert lane["child_run_id"] in _runs

        # Drive remaining lane to completion
        second_child_id = None
        for lane in result["lanes"]:
            child = _runs[lane["child_run_id"]]
            if child.status != "completed":
                second_child_id = lane["child_run_id"]
                break
        assert second_child_id is not None

        child_action = json.loads(_next(run_id=second_child_id))
        assert child_action["action"] == "prompt"
        child_result = json.loads(
            _submit(
                run_id=second_child_id,
                exec_key=child_action["exec_key"],
                output="checked second",
            )
        )
        assert child_result["action"] == "completed"

        # Submit parent parallel
        result = json.loads(
            _submit(
                run_id=run_id,
                exec_key=result["exec_key"],
                output="all lanes done",
            )
        )
        assert result["action"] == "completed"

    def test_resume_no_children_dir(self, parallel_prompt_workflow):
        """Resume works gracefully when no children/ directory exists (completed before parallel)."""
        # Create a simple non-parallel workflow to get a checkpoint without children
        wf_dir = parallel_prompt_workflow / "simple-cp"
        wf_dir.mkdir()
        (wf_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="simple-cp",
    description="Simple checkpoint test",
    blocks=[
        PromptStep(name="ask", prompt_type="confirm", message="OK?", result_var="a"),
        ShellStep(name="fin", command="echo done"),
    ],
)
""")
        start_result = json.loads(
            _start(
                workflow="simple-cp",
                cwd=str(parallel_prompt_workflow),
                workflow_dirs=[str(parallel_prompt_workflow)],
            )
        )
        run_id = start_result["run_id"]
        assert start_result["action"] == "ask_user"

        # Clear and resume -- no children dir, should work normally
        _runs.clear()
        result = json.loads(
            _start(
                workflow="simple-cp",
                cwd=str(parallel_prompt_workflow),
                workflow_dirs=[str(parallel_prompt_workflow)],
                resume=run_id,
            )
        )
        assert result["action"] == "ask_user"
        assert result["exec_key"] == "ask"

    def test_child_checkpoint_has_parallel_metadata(self, parallel_prompt_workflow):
        """Child checkpoints contain parallel_block_name and lane_index."""
        start_result = json.loads(
            _start(
                workflow="par-resume",
                cwd=str(parallel_prompt_workflow),
                workflow_dirs=[str(parallel_prompt_workflow)],
            )
        )
        run_id = start_result["run_id"]
        lanes = start_result["lanes"]

        children_dir = (
            parallel_prompt_workflow / ".workflow-state" / run_id / "children"
        )
        for i, lane in enumerate(lanes):
            child_id = lane["child_run_id"]
            # Composite ID: parent>child_hex -> child dir is just the segment after >
            child_segment = child_id.split(">")[-1]
            cp_file = children_dir / child_segment / "state.json"
            data = json.loads(cp_file.read_text())
            assert data["parallel_block_name"] == "checks"
            assert data["lane_index"] == i
            # Composite run_id encodes parent
            assert ">" in data["run_id"]

    def test_child_meta_has_block_label(self, parallel_prompt_workflow):
        """Child meta.json should have the block name with lane index."""
        start_result = json.loads(
            _start(
                workflow="par-resume",
                cwd=str(parallel_prompt_workflow),
                workflow_dirs=[str(parallel_prompt_workflow)],
            )
        )
        run_id = start_result["run_id"]
        lanes = start_result["lanes"]

        children_dir = (
            parallel_prompt_workflow / ".workflow-state" / run_id / "children"
        )
        for i, lane in enumerate(lanes):
            child_id = lane["child_run_id"]
            child_segment = child_id.split(">")[-1]
            meta_file = children_dir / child_segment / "meta.json"
            assert meta_file.exists(), f"meta.json missing for child {child_id}"
            meta = json.loads(meta_file.read_text())
            assert meta["workflow"] == f"checks[{i}]"
            assert meta["status"] == "running"
            assert meta["run_id"] == child_id


# ---------------------------------------------------------------------------
# Tests: Parallel auto-advance (shell-only lanes skip relay)
# ---------------------------------------------------------------------------


class TestParallelAutoAdvance:
    """Tests for parallel auto-advance: shell-only lanes complete without relay."""

    @pytest.fixture
    def par_shell_workflow(self, tmp_path):
        return _make_parallel_shell_only_workflow(tmp_path)

    @pytest.fixture
    def par_shell_no_trailing(self, tmp_path):
        return _make_parallel_shell_only_workflow(
            tmp_path,
            name="par-shell-nt",
            with_trailing_shell=False,
        )

    @pytest.fixture
    def par_shell_5_lanes(self, tmp_path):
        return _make_parallel_shell_only_workflow(
            tmp_path,
            name="par-shell-5",
            items_expr='["a", "b", "c", "d", "e"]',
        )

    def test_parallel_shell_only_skips_relay(self, par_shell_workflow):
        """Shell-only parallel lanes complete without emitting ParallelAction."""
        result = json.loads(
            _start(
                workflow="par-shell",
                cwd=str(par_shell_workflow),
                workflow_dirs=[str(par_shell_workflow)],
            )
        )
        # Should NOT be "parallel" -- all lanes are shell-only, auto-completed
        # Instead should advance past the parallel block to either the trailing
        # shell or completed
        assert result["action"] != "parallel", (
            f"Expected auto-advance past parallel block, got: {result['action']}"
        )
        # Should be completed (trailing shell auto-advances too)
        assert result["action"] == "completed"
        # Shell logs should include setup + all lane processes + trailing "done"
        shell_log = result.get("_shell_log", [])
        exec_keys = [s["exec_key"] for s in shell_log]
        assert "setup" in exec_keys
        assert "done" in exec_keys

    def test_parallel_mixed_returns_parallel_action(self, tmp_path):
        """Parallel with LLM template still returns ParallelAction for relay."""
        _make_parallel_workflow(tmp_path, name="par-mixed")
        result = json.loads(
            _start(
                workflow="par-mixed",
                cwd=str(tmp_path),
                workflow_dirs=[str(tmp_path)],
            )
        )
        assert result["action"] == "parallel"
        assert len(result["lanes"]) == 2

    def test_parallel_shell_only_results_collected(self, par_shell_no_trailing):
        """Parent results_scoped has merged child results after auto-completion."""
        result = json.loads(
            _start(
                workflow="par-shell-nt",
                cwd=str(par_shell_no_trailing),
                workflow_dirs=[str(par_shell_no_trailing)],
            )
        )
        assert result["action"] == "completed"
        run_id = result["run_id"]
        state = _runs[run_id]
        # The parallel block "checks" should have a result
        checks_result = state.ctx.results.get("checks")
        assert checks_result is not None

    def test_parallel_shell_only_lane_failure(self, tmp_path):
        """One lane fails -> parent auto-submits but with status=failure in result."""
        wf_dir = tmp_path / "par-fail"
        wf_dir.mkdir()
        # Use a 2-step template: first step always succeeds, second always fails.
        # Items list has 2 entries; the template has a step that uses 'false' to fail.
        (wf_dir / "workflow.py").write_text(r"""
WORKFLOW = WorkflowDef(
    name="par-fail",
    description="Parallel with failing lane",
    blocks=[
        ShellStep(
            name="setup",
            command='echo \'{"items": ["a", "b"]}\'',
            result_var="data",
        ),
        ParallelEachBlock(
            name="checks",
            template=[
                ShellStep(name="process", command="false"),
            ],
            parallel_for="variables.data.items",
        ),
    ],
)
""")
        result = json.loads(
            _start(
                workflow="par-fail",
                cwd=str(tmp_path),
                workflow_dirs=[str(tmp_path)],
            )
        )
        # Workflow should still complete (failure doesn't halt by default)
        assert result["action"] == "completed"
        run_id = result["run_id"]
        state = _runs[run_id]
        # The parallel block result should capture the failure
        checks_result = state.ctx.results.get("checks")
        assert checks_result is not None
        assert checks_result.status == "failure"

    def test_parallel_shell_log_deterministic_order(self, par_shell_5_lanes):
        """Shell logs from 5+ lanes are ordered by lane_index."""
        result = json.loads(
            _start(
                workflow="par-shell-5",
                cwd=str(par_shell_5_lanes),
                workflow_dirs=[str(par_shell_5_lanes)],
            )
        )
        assert result["action"] == "completed"
        shell_log = result.get("_shell_log", [])
        # Extract lane shell logs (exclude "setup" and "done")
        lane_logs = [s for s in shell_log if s["exec_key"] not in ("setup", "done")]
        # Should have 5 lane entries
        assert len(lane_logs) == 5
        # Exec keys should be in lane order: par:checks[i=0]/process, par:checks[i=1]/process, ...
        for i, log_entry in enumerate(lane_logs):
            assert log_entry["exec_key"] == f"par:checks[i={i}]/process"

    def test_parallel_child_meta_written(self, par_shell_workflow):
        """After fast-path, each child has a meta.json with terminal status."""
        result = json.loads(
            _start(
                workflow="par-shell",
                cwd=str(par_shell_workflow),
                workflow_dirs=[str(par_shell_workflow)],
            )
        )
        assert result["action"] == "completed"
        run_id = result["run_id"]

        # Check child meta.json files
        children_dir = par_shell_workflow / ".workflow-state" / run_id / "children"
        assert children_dir.exists(), "children dir must exist after parallel fast-path"
        child_dirs = list(children_dir.iterdir())
        assert len(child_dirs) == 3  # items: a, b, c
        for child_dir in child_dirs:
            meta_path = child_dir / "meta.json"
            assert meta_path.exists(), f"meta.json missing in {child_dir}"
            meta = json.loads(meta_path.read_text())
            assert meta["status"] in ("completed", "error", "halted")

    def test_parallel_parent_meta_updated(self, par_shell_no_trailing):
        """After fast-path, parent meta.json has terminal status (not stuck at running)."""
        result = json.loads(
            _start(
                workflow="par-shell-nt",
                cwd=str(par_shell_no_trailing),
                workflow_dirs=[str(par_shell_no_trailing)],
            )
        )
        assert result["action"] == "completed"
        run_id = result["run_id"]

        meta_path = par_shell_no_trailing / ".workflow-state" / run_id / "meta.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["status"] == "completed"

    def test_parallel_auto_advance_disabled(self, par_shell_workflow, monkeypatch):
        """MEMENTO_PARALLEL_AUTO_ADVANCE=off -> returns ParallelAction even for shell-only."""
        # Need a fresh runner namespace with the env var set
        monkeypatch.setenv("MEMENTO_PARALLEL_AUTO_ADVANCE", "off")
        ns = create_runner_ns()
        assert ns["_PARALLEL_AUTO_ADVANCE"] is False
        _start_off = ns["start"]
        _runs_off = ns["_runs"]

        result = json.loads(
            _start_off(
                workflow="par-shell",
                cwd=str(par_shell_workflow),
                workflow_dirs=[str(par_shell_workflow)],
            )
        )
        assert result["action"] == "parallel"
        assert len(result["lanes"]) == 3  # 3 items: a, b, c
        _runs_off.clear()

    def test_parallel_lane_exception_isolated(self, tmp_path):
        """One lane throws during advance -> ErrorAction, others complete, parent status=failure."""
        _make_parallel_shell_only_workflow(tmp_path, name="par-exc")

        # Patch advance() to throw for lane_index == 1
        original_advance = _runner_ns["advance"]

        def patched_advance(state):
            if state.parallel_block_name == "checks" and state.lane_index == 1:
                raise RuntimeError("synthetic lane failure")
            return original_advance(state)

        _runner_ns["advance"] = patched_advance
        try:
            result = json.loads(
                _start(
                    workflow="par-exc",
                    cwd=str(tmp_path),
                    workflow_dirs=[str(tmp_path)],
                )
            )
            # Should still complete (fast path handles ErrorAction lanes)
            assert result["action"] == "completed"
            run_id = result["run_id"]
            state = _runs[run_id]
            # The parallel block result should have failure status
            checks_result = state.ctx.results.get("checks")
            assert checks_result is not None
            assert checks_result.status == "failure"
        finally:
            _runner_ns["advance"] = original_advance


# ============ Thread-safety for _runs_lock ============


class TestRunsLockThreadSafety:
    """Dedicated thread-safety test for _runs_lock."""

    def test_concurrent_store_and_get(self, tmp_path):
        """Multiple threads can store and get runs concurrently without error."""
        import threading

        _store_run = _runner_ns["_store_run"]
        _get_run = _runner_ns["_get_run"]

        WorkflowContext = _types_ns["WorkflowContext"]
        RunState = _runner_ns["RunState"]

        errors = []
        n_threads = 10
        n_ops = 50

        def worker(thread_id):
            try:
                for i in range(n_ops):
                    run_id = f"run_{thread_id}_{i}"
                    ctx = WorkflowContext(cwd=str(tmp_path))
                    state = RunState(
                        run_id=run_id,
                        ctx=ctx,
                        stack=[],
                        registry={},
                        workflow_name="test",
                    )
                    _store_run(state)
                    retrieved = _get_run(run_id)
                    assert retrieved is not None, f"Failed to retrieve {run_id}"
                    assert retrieved.run_id == run_id
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread-safety errors: {errors}"
        assert len(_runs) == n_threads * n_ops

    def test_concurrent_store_and_cleanup(self, tmp_path):
        """Concurrent store + pop (cleanup) should not raise."""
        import threading

        _store_run = _runner_ns["_store_run"]
        _runs_lock = _runner_ns["_runs_lock"]

        WorkflowContext = _types_ns["WorkflowContext"]
        RunState = _runner_ns["RunState"]

        errors = []

        def storer():
            try:
                for i in range(100):
                    ctx = WorkflowContext(cwd=str(tmp_path))
                    state = RunState(
                        run_id=f"store_{i}",
                        ctx=ctx,
                        stack=[],
                        registry={},
                        workflow_name="test",
                    )
                    _store_run(state)
            except Exception as exc:
                errors.append(exc)

        def cleaner():
            try:
                for i in range(100):
                    with _runs_lock:
                        _runs.pop(f"store_{i}", None)
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=storer)
        t2 = threading.Thread(target=cleaner)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors, f"Thread-safety errors: {errors}"


# ============ Parallel fast path parent-not-found ============


class TestParallelFastPathParentNotFound:
    """_try_parallel_fast_path parent-not-found branch."""

    def test_returns_none_when_parent_missing(self, tmp_path):
        """When the parent run is not in _runs, fast path returns None."""
        _try_parallel_fast_path = _runner_ns["_try_parallel_fast_path"]
        ParallelAction = _runner_ns["ParallelAction"]
        CompletedAction = _runner_ns["CompletedAction"]
        WorkflowContext = _types_ns["WorkflowContext"]
        RunState = _runner_ns["RunState"]

        action = ParallelAction(
            run_id="nonexistent_parent",
            exec_key="test/parallel",
            lanes=[],
        )
        child_ctx = WorkflowContext(cwd=str(tmp_path))
        child = RunState(
            run_id="child1",
            ctx=child_ctx,
            stack=[],
            registry={},
            workflow_name="test",
        )
        child_action = CompletedAction(run_id="child1", summary={}, totals={})
        results = [(child, child_action, [])]

        result = _try_parallel_fast_path(action, results)
        assert result is None

    def test_succeeds_when_parent_exists(self, tmp_path):
        """When parent exists and all lanes terminal, fast path returns JSON."""
        _try_parallel_fast_path = _runner_ns["_try_parallel_fast_path"]
        _store_run = _runner_ns["_store_run"]
        ParallelAction = _runner_ns["ParallelAction"]
        CompletedAction = _runner_ns["CompletedAction"]
        Frame = _runner_ns["Frame"]
        WorkflowContext = _types_ns["WorkflowContext"]
        RunState = _runner_ns["RunState"]
        ShellStep = _types_ns["ShellStep"]
        ParallelEachBlock = _types_ns["ParallelEachBlock"]
        WorkflowDef = _types_ns["WorkflowDef"]

        parent_ctx = WorkflowContext(cwd=str(tmp_path))
        parent_wf = WorkflowDef(
            name="test",
            description="t",
            blocks=[
                ParallelEachBlock(
                    name="par",
                    parallel_for="variables.items",
                    item_var="item",
                    template=[ShellStep(name="cmd", command="echo ok")],
                ),
            ],
        )
        parent = RunState(
            run_id="parent1",
            ctx=parent_ctx,
            stack=[Frame(block=parent_wf)],
            registry={"test": parent_wf},
            workflow_name="test",
            checkpoint_dir=tmp_path / ".workflow-state" / "parent1",
        )
        _store_run(parent)

        action = ParallelAction(
            run_id="parent1",
            exec_key="par",
            lanes=[],
        )
        parent.pending_exec_key = "par"
        parent._last_action = action

        child_ctx = WorkflowContext(cwd=str(tmp_path))
        child = RunState(
            run_id="parent1>child1",
            ctx=child_ctx,
            stack=[],
            registry={},
            workflow_name="test",
            checkpoint_dir=tmp_path / ".workflow-state" / "parent1>child1",
        )
        child.status = "completed"
        _store_run(child)

        child_action = CompletedAction(run_id="parent1>child1", summary={}, totals={})
        results = [(child, child_action, [])]

        result = _try_parallel_fast_path(action, results)
        assert result is not None
        parsed = json.loads(result)
        assert "action" in parsed
