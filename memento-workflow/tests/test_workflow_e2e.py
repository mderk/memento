"""End-to-end relay loop tests for the workflow engine.

Simulates the full relay protocol: start → execute actions → submit → ... → completed.
Shell steps are executed internally by the MCP server (auto-advanced). The relay
only sees ask_user, prompt, subagent, and parallel actions. Shell execution
details are available in `_shell_log` on returned actions.
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
_runs = _runner_ns["_runs"]

# Types
ShellStep = _types_ns["ShellStep"]
PromptStep = _types_ns["PromptStep"]
LLMStep = _types_ns["LLMStep"]
GroupBlock = _types_ns["GroupBlock"]
LoopBlock = _types_ns["LoopBlock"]
RetryBlock = _types_ns["RetryBlock"]
ConditionalBlock = _types_ns["ConditionalBlock"]
Branch = _types_ns["Branch"]
SubWorkflow = _types_ns["SubWorkflow"]
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


def _create_workflow(tmp_path: Path, name: str, code: str) -> Path:
    """Helper to create a workflow in a temp directory."""
    wf_dir = tmp_path / name
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / "workflow.py").write_text(code)
    return tmp_path


def _collect_shell_log(action: dict) -> list[dict]:
    """Extract _shell_log entries from an action (empty list if absent)."""
    return action.get("_shell_log", [])


def _relay_loop(
    tmp_path: Path,
    workflow_name: str,
    *,
    preset_answers: dict[str, str] | None = None,
    prompt_responses: dict[str, str] | None = None,
    variables: dict | None = None,
    extra_dirs: list[str] | None = None,
    max_steps: int = 100,
) -> tuple[list[dict], dict, list[dict]]:
    """Run a full relay loop and return (actions_executed, final_result, all_shell_logs).

    Shell steps are auto-advanced by the MCP server — not visible as actions.
    Ask_user steps use preset_answers.
    Prompt (LLM) steps use prompt_responses.
    Returns all shell log entries collected across all actions.
    """
    preset = preset_answers or {}
    prompts = prompt_responses or {}
    variables = variables or {}
    dirs = extra_dirs or [str(tmp_path)]

    start_result = json.loads(_start(
        workflow=workflow_name,
        cwd=str(tmp_path),
        workflow_dirs=dirs,
        variables=variables,
    ))
    if start_result["action"] == "error":
        return [], start_result, []

    run_id = start_result["run_id"]
    action = start_result
    executed = []
    all_shell_logs: list[dict] = []
    steps = 0

    # Collect shell logs from start action
    all_shell_logs.extend(_collect_shell_log(action))

    while action["action"] not in ("completed", "error", "cancelled"):
        steps += 1
        if steps > max_steps:
            raise RuntimeError(f"Relay loop exceeded {max_steps} steps")

        exec_key = action["exec_key"]
        executed.append(action)

        if action["action"] == "ask_user":
            answer = preset.get(exec_key, action.get("default", "yes"))
            action = json.loads(_submit(
                run_id=run_id,
                exec_key=exec_key,
                output=answer,
            ))

        elif action["action"] == "prompt":
            response = prompts.get(exec_key, f"[prompt response for {exec_key}]")
            action = json.loads(_submit(
                run_id=run_id,
                exec_key=exec_key,
                output=response,
            ))

        elif action["action"] == "subagent":
            # Simulate subagent: for relay=true, run sub-relay; for relay=false, return fake output
            if action.get("relay"):
                child_run_id = action["child_run_id"]
                child_action = json.loads(_next(run_id=child_run_id))
                child_outputs = []
                # Collect child's initial shell logs
                all_shell_logs.extend(_collect_shell_log(child_action))
                while child_action["action"] not in ("completed", "error", "cancelled"):
                    child_exec_key = child_action["exec_key"]
                    if child_action["action"] == "ask_user":
                        c_out = preset.get(child_exec_key, child_action.get("default", "yes"))
                        c_status = "success"
                    elif child_action["action"] == "prompt":
                        c_out = prompts.get(child_exec_key, f"[sub-prompt for {child_exec_key}]")
                        c_status = "success"
                    else:
                        c_out = f"[sub-{child_action['action']}]"
                        c_status = "success"
                    child_outputs.append(c_out)
                    child_action = json.loads(_submit(
                        run_id=child_run_id,
                        exec_key=child_exec_key,
                        output=c_out,
                        status=c_status,
                    ))
                    all_shell_logs.extend(_collect_shell_log(child_action))
                # Submit parent with sub-relay summary
                action = json.loads(_submit(
                    run_id=run_id,
                    exec_key=exec_key,
                    output="; ".join(child_outputs) or "sub-relay done",
                ))
            else:
                # Single-task subagent
                output = prompts.get(exec_key, f"[subagent output for {exec_key}]")
                action = json.loads(_submit(
                    run_id=run_id,
                    exec_key=exec_key,
                    output=output,
                ))

        elif action["action"] == "parallel":
            # Process parallel lanes sequentially (simulating parallel agents)
            lane_outputs = []
            for lane in action["lanes"]:
                child_run_id = lane["child_run_id"]
                child_action = json.loads(_next(run_id=child_run_id))
                lane_results = []
                all_shell_logs.extend(_collect_shell_log(child_action))
                while child_action["action"] not in ("completed", "error", "cancelled"):
                    child_exec_key = child_action["exec_key"]
                    if child_action["action"] == "prompt":
                        c_out = prompts.get(child_exec_key, f"[parallel-prompt for {child_exec_key}]")
                        c_status = "success"
                    elif child_action["action"] == "ask_user":
                        c_out = preset.get(child_exec_key, child_action.get("default", "yes"))
                        c_status = "success"
                    else:
                        c_out = f"[parallel-{child_action['action']}]"
                        c_status = "success"
                    lane_results.append(c_out)
                    child_action = json.loads(_submit(
                        run_id=child_run_id,
                        exec_key=child_exec_key,
                        output=c_out,
                        status=c_status,
                    ))
                    all_shell_logs.extend(_collect_shell_log(child_action))
                lane_outputs.append("; ".join(lane_results))

            action = json.loads(_submit(
                run_id=run_id,
                exec_key=exec_key,
                output=json.dumps(lane_outputs),
            ))

        else:
            raise RuntimeError(f"Unknown action type: {action['action']}")

        # Collect shell logs from the newly returned action
        all_shell_logs.extend(_collect_shell_log(action))

        # Verify checkpoint exists after each submit
        state_dir = tmp_path / ".workflow-state" / run_id
        if action["action"] not in ("error",):
            assert state_dir.exists(), "Checkpoint dir missing after submit"
            assert (state_dir / "state.json").exists(), "state.json missing"

    return executed, action, all_shell_logs


# ---------------------------------------------------------------------------
# Tests: Simple relay loop
# ---------------------------------------------------------------------------


class TestSimpleRelay:
    def test_two_shell_steps_complete_immediately(self, tmp_path):
        """Shell-only workflow completes on start() — no relay steps needed."""
        _create_workflow(tmp_path, "simple", """
WORKFLOW = WorkflowDef(
    name="simple",
    description="Two echo steps",
    blocks=[
        ShellStep(name="step1", command="echo hello"),
        ShellStep(name="step2", command="echo world"),
    ],
)
""")
        executed, final, shell_logs = _relay_loop(tmp_path, "simple")
        assert final["action"] == "completed"
        # No relay actions needed (all shell → auto-advanced)
        assert len(executed) == 0
        # Shell steps visible in _shell_log
        assert len(shell_logs) == 2
        assert shell_logs[0]["exec_key"] == "step1"
        assert shell_logs[1]["exec_key"] == "step2"

    def test_shell_with_result_var(self, tmp_path):
        """Shell step with result_var parses JSON into variables (visible in ask_user)."""
        _create_workflow(tmp_path, "result-var", r"""
WORKFLOW = WorkflowDef(
    name="result-var",
    description="Shell with result_var",
    blocks=[
        ShellStep(
            name="detect",
            command='echo \'{"count": 3}\'',
            result_var="detection",
        ),
        PromptStep(
            name="confirm",
            prompt_type="confirm",
            message="Found {{variables.detection.count}} items",
            result_var="answer",
        ),
    ],
)
""")
        executed, final, shell_logs = _relay_loop(
            tmp_path, "result-var",
            preset_answers={"confirm": "yes"},
        )
        assert final["action"] == "completed"
        # Only ask_user was a relay action
        assert len(executed) == 1
        assert executed[0]["action"] == "ask_user"
        # result_var substituted in message
        assert "3" in executed[0]["message"]
        # Shell in _shell_log
        assert shell_logs[0]["exec_key"] == "detect"

    def test_ask_user_with_preset(self, tmp_path):
        """Ask_user steps use preset answers."""
        _create_workflow(tmp_path, "ask-test", """
WORKFLOW = WorkflowDef(
    name="ask-test",
    description="Workflow with ask_user",
    blocks=[
        PromptStep(
            name="confirm",
            prompt_type="confirm",
            message="Proceed?",
            default="yes",
            result_var="answer",
        ),
        ShellStep(name="done", command="echo done"),
    ],
)
""")
        executed, final, shell_logs = _relay_loop(
            tmp_path, "ask-test",
            preset_answers={"confirm": "yes"},
        )
        assert final["action"] == "completed"
        assert executed[0]["action"] == "ask_user"
        # Trailing shell in _shell_log
        assert shell_logs[0]["exec_key"] == "done"


# ---------------------------------------------------------------------------
# Tests: Conditional branching
# ---------------------------------------------------------------------------


class TestConditionalRelay:
    def test_conditional_first_branch(self, tmp_path):
        """Conditional takes first matching branch."""
        _create_workflow(tmp_path, "cond-test", """
WORKFLOW = WorkflowDef(
    name="cond-test",
    description="Conditional branching",
    blocks=[
        PromptStep(
            name="mode",
            prompt_type="choice",
            message="Pick mode:",
            options=["fast", "slow"],
            result_var="mode_var",
        ),
        ConditionalBlock(
            name="mode-branch",
            branches=[
                Branch(
                    condition=lambda ctx: ctx.variables.get("mode_var") == "fast",
                    blocks=[ShellStep(name="fast-path", command="echo fast")],
                ),
                Branch(
                    condition=lambda ctx: ctx.variables.get("mode_var") == "slow",
                    blocks=[ShellStep(name="slow-path", command="echo slow")],
                ),
            ],
            default=[ShellStep(name="default-path", command="echo default")],
        ),
    ],
)
""")
        executed, final, shell_logs = _relay_loop(
            tmp_path, "cond-test",
            preset_answers={"mode": "fast"},
        )
        assert final["action"] == "completed"
        shell_keys = [s["exec_key"] for s in shell_logs]
        assert "fast-path" in shell_keys
        assert "slow-path" not in shell_keys

    def test_conditional_default(self, tmp_path):
        """Conditional falls through to default."""
        _create_workflow(tmp_path, "cond-default", """
WORKFLOW = WorkflowDef(
    name="cond-default",
    description="Conditional with default",
    blocks=[
        PromptStep(
            name="mode",
            prompt_type="choice",
            message="Pick:",
            options=["a", "b"],
            result_var="mode_var",
        ),
        ConditionalBlock(
            name="branch",
            branches=[
                Branch(
                    condition=lambda ctx: ctx.variables.get("mode_var") == "x",
                    blocks=[ShellStep(name="branch-x", command="echo x")],
                ),
            ],
            default=[ShellStep(name="fallback", command="echo fallback")],
        ),
    ],
)
""")
        executed, final, shell_logs = _relay_loop(
            tmp_path, "cond-default",
            preset_answers={"mode": "a"},
        )
        assert final["action"] == "completed"
        shell_keys = [s["exec_key"] for s in shell_logs]
        assert "fallback" in shell_keys
        assert "branch-x" not in shell_keys


# ---------------------------------------------------------------------------
# Tests: Loop
# ---------------------------------------------------------------------------


class TestLoopRelay:
    def test_loop_iterates(self, tmp_path):
        """LoopBlock iterates over items — shell iterations auto-advanced."""
        _create_workflow(tmp_path, "loop-test", r"""
WORKFLOW = WorkflowDef(
    name="loop-test",
    description="Loop over items",
    blocks=[
        ShellStep(
            name="setup",
            command='echo \'{"items": ["a", "b", "c"]}\'',
            result_var="data",
        ),
        LoopBlock(
            name="process",
            loop_over="variables.data.items",
            loop_var="item",
            blocks=[
                ShellStep(
                    name="handle",
                    command="echo 'item={{variables.item}}'",
                ),
            ],
        ),
    ],
)
""")
        executed, final, shell_logs = _relay_loop(tmp_path, "loop-test")
        assert final["action"] == "completed"
        # All shell steps auto-advanced — no relay actions
        assert len(executed) == 0
        # setup + 3 loop iterations = 4 shell log entries
        assert len(shell_logs) == 4
        loop_keys = [s["exec_key"] for s in shell_logs[1:]]
        assert "loop:process[i=0]/handle" in loop_keys
        assert "loop:process[i=1]/handle" in loop_keys
        assert "loop:process[i=2]/handle" in loop_keys


# ---------------------------------------------------------------------------
# Tests: Retry
# ---------------------------------------------------------------------------


class TestRetryRelay:
    def test_retry_succeeds_on_third_attempt(self, tmp_path):
        """RetryBlock retries until success — all auto-advanced."""
        counter_file = tmp_path / "attempt_counter"
        _create_workflow(tmp_path, "retry-test", f"""
WORKFLOW = WorkflowDef(
    name="retry-test",
    description="Retry with counter",
    blocks=[
        RetryBlock(
            name="flaky",
            max_attempts=5,
            until=lambda ctx: (
                ctx.results.get("try-cmd") is not None
                and ctx.results["try-cmd"].status == "success"
            ),
            blocks=[
                ShellStep(
                    name="try-cmd",
                    command=(
                        "COUNT=$(cat {counter_file} 2>/dev/null || echo 0) && "
                        "COUNT=$((COUNT + 1)) && "
                        "echo $COUNT > {counter_file} && "
                        "if [ $COUNT -lt 3 ]; then echo 'not yet' >&2 && exit 1; else echo 'OK'; fi"
                    ),
                ),
            ],
        ),
    ],
)
""")
        executed, final, shell_logs = _relay_loop(tmp_path, "retry-test")
        assert final["action"] == "completed"
        # All shell — no relay actions
        assert len(executed) == 0
        # Should have 3 attempts in shell_log (fail, fail, success)
        assert len(shell_logs) == 3
        assert "retry:flaky[attempt=2]/try-cmd" in shell_logs[-1]["exec_key"]


# ---------------------------------------------------------------------------
# Tests: SubWorkflow
# ---------------------------------------------------------------------------


class TestSubWorkflowRelay:
    def test_subworkflow_calls_helper(self, tmp_path):
        """SubWorkflow invokes a separate workflow — shell steps auto-advanced."""
        # Create helper sub-workflow
        helper_dir = tmp_path / "test-helper"
        helper_dir.mkdir()
        (helper_dir / "workflow.py").write_text("""
WORKFLOW = WorkflowDef(
    name="test-helper",
    description="Helper workflow",
    blocks=[
        ShellStep(name="helper-echo", command="echo '{{variables.input_val}}'"),
    ],
)
""")
        # Create main workflow
        _create_workflow(tmp_path, "main-wf", """
WORKFLOW = WorkflowDef(
    name="main-wf",
    description="Main with subworkflow",
    blocks=[
        ShellStep(name="pre", command="echo before"),
        SubWorkflow(
            name="call-helper",
            workflow="test-helper",
            inject={"input_val": "injected-value"},
        ),
        ShellStep(name="post", command="echo after"),
    ],
)
""")
        executed, final, shell_logs = _relay_loop(tmp_path, "main-wf")
        assert final["action"] == "completed"
        # All shell — no relay actions
        assert len(executed) == 0
        shell_keys = [s["exec_key"] for s in shell_logs]
        assert "pre" in shell_keys
        assert "sub:call-helper/helper-echo" in shell_keys
        assert "post" in shell_keys


# ---------------------------------------------------------------------------
# Tests: Condition skipping
# ---------------------------------------------------------------------------


class TestConditionSkip:
    def test_skipped_steps_not_executed(self, tmp_path):
        """Blocks with false conditions are skipped."""
        _create_workflow(tmp_path, "skip-test", """
WORKFLOW = WorkflowDef(
    name="skip-test",
    description="Skip via condition",
    blocks=[
        ShellStep(name="always-runs", command="echo yes"),
        ShellStep(
            name="never-runs",
            command="echo BUG",
            condition=lambda ctx: False,
        ),
        ShellStep(name="also-runs", command="echo yes2"),
    ],
)
""")
        executed, final, shell_logs = _relay_loop(tmp_path, "skip-test")
        assert final["action"] == "completed"
        shell_keys = [s["exec_key"] for s in shell_logs]
        assert "always-runs" in shell_keys
        assert "also-runs" in shell_keys
        assert "never-runs" not in shell_keys


# ---------------------------------------------------------------------------
# Tests: Failure + recovery
# ---------------------------------------------------------------------------


class TestFailureRecovery:
    def test_failure_recorded_then_recovery(self, tmp_path):
        """Failed shell step recorded, recovery step runs based on condition."""
        _create_workflow(tmp_path, "fail-recover", """
WORKFLOW = WorkflowDef(
    name="fail-recover",
    description="Failure recovery",
    blocks=[
        ShellStep(name="fail-step", command="echo 'oops' >&2 && exit 1"),
        ShellStep(
            name="recovery",
            command="echo recovered",
            condition=lambda ctx: (
                ctx.results.get("fail-step") is not None
                and ctx.results["fail-step"].status == "failure"
            ),
        ),
        ShellStep(
            name="skip-if-failed",
            command="echo BUG",
            condition=lambda ctx: (
                ctx.results.get("fail-step") is not None
                and ctx.results["fail-step"].status == "success"
            ),
        ),
    ],
)
""")
        executed, final, shell_logs = _relay_loop(tmp_path, "fail-recover")
        assert final["action"] == "completed"
        shell_keys = [s["exec_key"] for s in shell_logs]
        assert "fail-step" in shell_keys
        assert "recovery" in shell_keys
        assert "skip-if-failed" not in shell_keys
        # Verify failure status in log
        fail_entry = next(s for s in shell_logs if s["exec_key"] == "fail-step")
        assert fail_entry["status"] == "failure"


# ---------------------------------------------------------------------------
# Tests: Checkpoint verification
# ---------------------------------------------------------------------------


class TestCheckpointE2E:
    def test_checkpoint_exists_for_shell_only(self, tmp_path):
        """Checkpoint file created even for immediately-completing workflows."""
        _create_workflow(tmp_path, "cp-test", """
WORKFLOW = WorkflowDef(
    name="cp-test",
    description="Checkpoint test",
    blocks=[
        ShellStep(name="s1", command="echo 1"),
        ShellStep(name="s2", command="echo 2"),
        ShellStep(name="s3", command="echo 3"),
    ],
)
""")
        executed, final, shell_logs = _relay_loop(tmp_path, "cp-test")
        assert final["action"] == "completed"
        assert len(shell_logs) == 3
        # Checkpoint should exist
        state_dir = tmp_path / ".workflow-state"
        assert state_dir.exists()
        run_dirs = list(state_dir.iterdir())
        assert len(run_dirs) >= 1

    def test_checkpoint_contains_valid_json(self, tmp_path):
        """Checkpoint file contains valid JSON with expected fields."""
        _create_workflow(tmp_path, "cp-json", """
WORKFLOW = WorkflowDef(
    name="cp-json",
    description="Checkpoint JSON test",
    blocks=[
        ShellStep(name="s1", command="echo hello"),
        PromptStep(name="ask", prompt_type="confirm", message="OK?", result_var="a"),
    ],
)
""")
        start_result = json.loads(_start(
            workflow="cp-json",
            cwd=str(tmp_path),
            workflow_dirs=[str(tmp_path)],
        ))
        run_id = start_result["run_id"]
        # Shell auto-advanced, now at ask_user
        assert start_result["action"] == "ask_user"

        # Read and verify checkpoint
        cp_file = tmp_path / ".workflow-state" / run_id / "state.json"
        assert cp_file.exists()
        data = json.loads(cp_file.read_text())

        assert data["run_id"] == run_id
        assert "ctx" in data
        # Shell step "s1" was auto-advanced and recorded
        assert "s1" in data["ctx"]["results_scoped"]
        assert data["ctx"]["results_scoped"]["s1"]["status"] == "success"


# ---------------------------------------------------------------------------
# Tests: LLM prompt action
# ---------------------------------------------------------------------------


class TestLLMPromptRelay:
    def test_llm_step_returns_prompt_action(self, tmp_path):
        """LLMStep emits a prompt action that the relay processes inline."""
        prompts_dir = tmp_path / "llm-wf" / "prompts"
        prompts_dir.mkdir(parents=True)
        (prompts_dir / "analyze.md").write_text("Analyze the following: {{variables.topic}}")
        _create_workflow(tmp_path, "llm-wf", """
WORKFLOW = WorkflowDef(
    name="llm-wf",
    description="LLM prompt test",
    blocks=[
        LLMStep(name="analyze", prompt="analyze.md", model="haiku"),
        ShellStep(name="done", command="echo done"),
    ],
)
""")
        executed, final, shell_logs = _relay_loop(
            tmp_path, "llm-wf",
            variables={"topic": "testing"},
            prompt_responses={"analyze": "Analysis complete"},
        )
        assert final["action"] == "completed"
        assert executed[0]["action"] == "prompt"
        assert "testing" in executed[0]["prompt"]
        # Trailing shell in _shell_log
        assert shell_logs[0]["exec_key"] == "done"


# ---------------------------------------------------------------------------
# Tests: Group with subagent isolation
# ---------------------------------------------------------------------------


class TestGroupSubagentRelay:
    def test_subagent_group_emits_subagent_action(self, tmp_path):
        """GroupBlock with isolation=subagent emits subagent action with child_run_id."""
        prompts_dir = tmp_path / "group-wf" / "prompts"
        prompts_dir.mkdir(parents=True)
        (prompts_dir / "step1.md").write_text("Step 1 prompt")
        (prompts_dir / "step2.md").write_text("Step 2 prompt")
        _create_workflow(tmp_path, "group-wf", """
WORKFLOW = WorkflowDef(
    name="group-wf",
    description="Subagent group test",
    blocks=[
        ShellStep(name="pre", command="echo before"),
        GroupBlock(
            name="sub-group",
            isolation="subagent",
            context_hint="test context",
            blocks=[
                LLMStep(name="inner1", prompt="step1.md", model="haiku"),
                LLMStep(name="inner2", prompt="step2.md", model="haiku"),
            ],
        ),
        ShellStep(name="post", command="echo after"),
    ],
)
""")
        executed, final, shell_logs = _relay_loop(
            tmp_path, "group-wf",
            prompt_responses={
                "inner1": "inner1 done",
                "inner2": "inner2 done",
            },
        )
        assert final["action"] == "completed"
        # Shell "pre" was auto-advanced before subagent
        shell_keys = [s["exec_key"] for s in shell_logs]
        assert "pre" in shell_keys
        # Subagent action was the first relay action
        assert executed[0]["action"] == "subagent"
        assert executed[0]["relay"] is True
        assert "child_run_id" in executed[0]
        # Shell "post" was auto-advanced after subagent
        assert "post" in shell_keys


# ---------------------------------------------------------------------------
# Tests: Real test-workflow (quick mode)
# ---------------------------------------------------------------------------

# Paths to the real test-workflow and its sub-workflows
_TEST_WORKFLOW_DIR = (
    Path(__file__).resolve().parent.parent / "skills" / "test-workflow"
)
_TEST_SUBWORKFLOWS_DIR = _TEST_WORKFLOW_DIR / "sub-workflows"


class TestRealTestWorkflow:
    """Run the actual skills/test-workflow in quick mode through the relay loop.

    This exercises all 9 block types on real workflow definitions with real
    shell commands (auto-advanced by MCP server), real sub-workflow discovery,
    and real condition evaluation.

    Quick mode path:
      Phase 1:  detect (shell → auto-advanced)
      Phase 2:  mode (ask_user → "quick")
      Phase 3:  mode-branch (conditional → quick-run → auto-advanced)
      Phase 4:  process-items (loop × 3 → auto-advanced)
      Phase 5:  risky-step (failure) → recovery (conditional → auto-advanced)
      Phase 6:  setup-counter-dir (shell → auto-advanced)
      Phase 7:  retry-flaky (retry × 3 → auto-advanced)
      Phase 8:  call-helper (subworkflow: helper-echo + helper-transform → auto-advanced)
      Phase 9:  loop-retry-items (loop × 3, each retry × 2 → auto-advanced)
      Phase 10-16: skipped (mode≠thorough, enable_llm not set)
      Phase 17: final-decision (ask_user → "accept")
      Phase 18: confirm-results (ask_user → "yes") + finalize + cleanup (auto-advanced)
    """

    def test_discovery(self, tmp_path):
        """list_workflows discovers test-workflow and test-helper."""
        result = json.loads(_list_workflows(
            cwd=str(tmp_path),
            workflow_dirs=[str(_TEST_WORKFLOW_DIR), str(_TEST_SUBWORKFLOWS_DIR)],
        ))
        names = [w["name"] for w in result["workflows"]]
        assert "test-workflow" in names
        assert "test-helper" in names

    def test_quick_mode_full_relay(self, tmp_path):
        """Full relay loop of test-workflow in quick mode — all 9 block types."""
        executed, final, shell_logs = _relay_loop(
            tmp_path,
            "test-workflow",
            preset_answers={
                "mode": "quick",
                "final-decision": "accept",
                "confirm-results": "yes",
            },
            extra_dirs=[str(_TEST_WORKFLOW_DIR), str(_TEST_SUBWORKFLOWS_DIR)],
            max_steps=200,
        )
        assert final["action"] == "completed", f"Workflow did not complete: {final}"

        # Relay actions: only ask_user steps should be visible
        relay_keys = {a["exec_key"]: a["action"] for a in executed}
        shell_keys = {s["exec_key"] for s in shell_logs}

        # Phase 1: detection with result_var → auto-advanced
        assert "detect" in shell_keys

        # Phase 2: mode choice → relay action
        assert relay_keys.get("mode") == "ask_user"

        # Phase 3: conditional took quick branch → auto-advanced
        assert "quick-run" in shell_keys
        assert "fallback" not in shell_keys

        # Phase 4: loop over 3 items → auto-advanced
        assert "loop:process-items[i=0]/process" in shell_keys
        assert "loop:process-items[i=1]/process" in shell_keys
        assert "loop:process-items[i=2]/process" in shell_keys

        # Phase 5: failure + recovery → auto-advanced
        assert "risky-step" in shell_keys
        assert "recovery" in shell_keys
        assert "skip-on-success" not in shell_keys

        # Phase 6: setup counter dir → auto-advanced
        assert "setup-counter-dir" in shell_keys

        # Phase 7: retry — flaky-cmd retries until success → auto-advanced
        retry_keys = [k for k in shell_keys if "retry-flaky" in k and "flaky-cmd" in k]
        assert len(retry_keys) >= 3

        # Phase 8: subworkflow (test-helper) → auto-advanced
        assert "sub:call-helper/helper-echo" in shell_keys
        assert "sub:call-helper/helper-transform" in shell_keys

        # Phase 9: loop × retry combo → auto-advanced
        for item_idx in range(3):
            prefix = f"loop:loop-retry-items[i={item_idx}]/retry:item-retry"
            item_keys = [k for k in shell_keys if k.startswith(prefix)]
            assert len(item_keys) >= 2, f"Expected ≥2 attempts for item {item_idx}, got {item_keys}"

        # Phases 10-16: all skipped (quick mode)
        llm_relay = [k for k in relay_keys if "llm-" in k or "session-" in k or "parallel-" in k]
        assert llm_relay == [], f"LLM/parallel should be skipped in quick mode: {llm_relay}"

        # Phase 17: final-decision → relay action
        assert relay_keys.get("final-decision") == "ask_user"

        # Phase 18: confirm + finalize + cleanup
        assert relay_keys.get("confirm-results") == "ask_user"
        assert "finalize" in shell_keys
        assert "cleanup" in shell_keys

    def test_quick_mode_checkpoint_persistence(self, tmp_path):
        """Checkpoint file exists after workflow completes."""
        executed, final, shell_logs = _relay_loop(
            tmp_path,
            "test-workflow",
            preset_answers={
                "mode": "quick",
                "final-decision": "accept",
                "confirm-results": "yes",
            },
            extra_dirs=[str(_TEST_WORKFLOW_DIR), str(_TEST_SUBWORKFLOWS_DIR)],
            max_steps=200,
        )
        assert final["action"] == "completed"

        # At least one checkpoint dir should exist
        state_dir = tmp_path / ".workflow-state"
        assert state_dir.exists()
        run_dirs = list(state_dir.iterdir())
        assert len(run_dirs) >= 1
        # Checkpoint file should have valid JSON
        cp_file = run_dirs[0] / "state.json"
        assert cp_file.exists()
        data = json.loads(cp_file.read_text())
        assert "ctx" in data
        assert "results_scoped" in data["ctx"]
        # Should have many recorded results
        assert len(data["ctx"]["results_scoped"]) >= 15

    def test_quick_mode_result_var_propagation(self, tmp_path):
        """result_var from detect propagates to downstream template substitution."""
        executed, final, shell_logs = _relay_loop(
            tmp_path,
            "test-workflow",
            preset_answers={
                "mode": "quick",
                "final-decision": "accept",
                "confirm-results": "yes",
            },
            extra_dirs=[str(_TEST_WORKFLOW_DIR), str(_TEST_SUBWORKFLOWS_DIR)],
            max_steps=200,
        )
        assert final["action"] == "completed"

        # Phase 4 loop items came from detect result_var
        loop_shells = [s for s in shell_logs if "process-items" in s["exec_key"]]
        assert len(loop_shells) == 3
        # Read commands from artifact files
        run_id = final["run_id"]
        art_base = tmp_path / ".workflow-state" / run_id / "artifacts"
        loop_commands = [
            (art_base / s["artifact"] / "command.txt").read_text()
            for s in loop_shells
        ]
        assert any("shell" in c for c in loop_commands)
        assert any("conditional" in c for c in loop_commands)
        assert any("retry" in c for c in loop_commands)

        # Phase 8 subworkflow receives injected count
        helper_echo = [s for s in shell_logs if s["exec_key"] == "sub:call-helper/helper-echo"]
        assert len(helper_echo) == 1
        helper_cmd = (art_base / helper_echo[0]["artifact"] / "command.txt").read_text()
        assert "3" in helper_cmd

    def test_reject_path(self, tmp_path):
        """Rejecting at confirm-results skips finalize and cleanup."""
        executed, final, shell_logs = _relay_loop(
            tmp_path,
            "test-workflow",
            preset_answers={
                "mode": "quick",
                "final-decision": "accept",
                "confirm-results": "no",
            },
            extra_dirs=[str(_TEST_WORKFLOW_DIR), str(_TEST_SUBWORKFLOWS_DIR)],
            max_steps=200,
        )
        assert final["action"] == "completed"

        relay_keys = [a["exec_key"] for a in executed]
        shell_keys = {s["exec_key"] for s in shell_logs}
        assert "confirm-results" in relay_keys
        # finalize and cleanup have condition: confirm-results.output != "no"
        # Since we answered "no", they should be skipped
        assert "finalize" not in shell_keys
        assert "cleanup" not in shell_keys
