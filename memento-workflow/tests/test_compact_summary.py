"""Tests for compact summary mode in CompletedAction."""

from conftest import _state_ns, _types_ns

# Types
WorkflowDef = _types_ns["WorkflowDef"]
WorkflowContext = _types_ns["WorkflowContext"]
StepResult = _types_ns["StepResult"]

# State / actions
Frame = _state_ns["Frame"]
RunState = _state_ns["RunState"]
CompletedAction = _state_ns["CompletedAction"]
action_to_dict = _state_ns["action_to_dict"]
_build_completed_action = _state_ns["_build_completed_action"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(tmp_path, num_results, *, include_failure=False):
    """Create RunState with N results."""
    wf = WorkflowDef(name="test", description="test", blocks=[])
    ctx = WorkflowContext(cwd=".")
    checkpoint_dir = tmp_path / "checkpoint"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    state = RunState(
        run_id="test-run",
        ctx=ctx,
        stack=[Frame(block=wf)],
        registry={"test": wf},
        wf_hash="test-hash",
        checkpoint_dir=checkpoint_dir,
    )
    # Add results
    for i in range(num_results):
        key = f"step{i}"
        status = "success"
        if include_failure and i == num_results - 1:
            status = "failure"
        r = StepResult(
            name=key,
            exec_key=key,
            base=key,
            results_key=key,
            status=status,
            output=f"output-{i}",
            step_type="llm_step",
            duration=1.0,
        )
        state.ctx.results[key] = r
        state.ctx.results_scoped[key] = r
    return state


# ---------------------------------------------------------------------------
# Tests: CompletedAction compact field
# ---------------------------------------------------------------------------


class TestCompactField:
    def test_completed_action_has_compact_field(self):
        """CompletedAction should have a compact field."""
        action = CompletedAction(run_id="test", compact=True)
        assert action.compact is True

    def test_compact_defaults_none(self):
        """compact defaults to None (omitted from wire)."""
        action = CompletedAction(run_id="test")
        assert action.compact is None

    def test_compact_omitted_from_dict_when_none(self):
        """action_to_dict should omit compact when None."""
        action = CompletedAction(run_id="test")
        d = action_to_dict(action)
        assert "compact" not in d

    def test_compact_included_in_dict_when_true(self):
        """action_to_dict should include compact when True."""
        action = CompletedAction(run_id="test", compact=True)
        d = action_to_dict(action)
        assert d["compact"] is True


# ---------------------------------------------------------------------------
# Tests: Compact mode behavior
# ---------------------------------------------------------------------------


class TestCompactModeBehavior:
    def test_below_threshold_full_summary(self, tmp_path):
        """Workflows with few results get full summary (no compact)."""
        state = _make_state(tmp_path, 5)
        action = _build_completed_action(state)
        assert action.compact is None or action.compact is False
        # All 5 steps should be in summary
        assert len(action.summary) == 5

    def test_above_threshold_compact_mode(self, tmp_path):
        """Workflows above threshold auto-switch to compact mode."""
        state = _make_state(tmp_path, 35)
        action = _build_completed_action(state)
        assert action.compact is True
        # Compact: only non-success entries in summary
        # All 35 are success, so summary should be empty or very small
        assert len(action.summary) < 35

    def test_compact_keeps_failures(self, tmp_path):
        """Compact mode retains non-success entries."""
        state = _make_state(tmp_path, 35, include_failure=True)
        action = _build_completed_action(state)
        assert action.compact is True
        # The failure step should be in summary
        failure_entries = {
            k: v for k, v in action.summary.items()
            if isinstance(v, dict) and v.get("status") != "success"
        }
        assert len(failure_entries) >= 1

    def test_compact_totals_always_complete(self, tmp_path):
        """Totals must include all steps regardless of compact mode."""
        state = _make_state(tmp_path, 35)
        action = _build_completed_action(state)
        assert action.totals["step_count"] == 35
