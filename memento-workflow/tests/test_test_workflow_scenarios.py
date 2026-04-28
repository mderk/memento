from __future__ import annotations

import json
from pathlib import Path

import pytest

from scenario_driver import load_scenario, run_engine_scenario

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "test-workflow"


def _load(name: str):
    return load_scenario(_FIXTURES_DIR / name)


def _exec_keys(run) -> list[str]:
    return [entry["exec_key"] for entry in run.transcript if entry.get("exec_key")]


def _shell_keys(run) -> set[str]:
    return {entry["exec_key"] for entry in run.shell_logs}


@pytest.mark.e2e
class TestTestWorkflowScenarios:
    def test_quick_accept_yes(self, tmp_path):
        scenario = _load("quick-accept-yes.json")
        run = run_engine_scenario(tmp_path, scenario)

        assert run.final_action["action"] == "completed"
        exec_keys = _exec_keys(run)
        shell_keys = _shell_keys(run)
        assert "mode" in exec_keys
        assert "final-decision" in exec_keys
        assert "confirm-results" in exec_keys
        assert "finalize" in shell_keys
        assert "cleanup" in shell_keys
        assert "llm-classify" not in exec_keys
        assert "llm-summarize" not in exec_keys
        assert not run.restart_events

    def test_quick_accept_no_skips_finalize_and_cleanup(self, tmp_path):
        scenario = _load("quick-accept-no.json")
        run = run_engine_scenario(tmp_path, scenario)

        assert run.final_action["action"] == "completed"
        shell_keys = _shell_keys(run)
        assert "finalize" not in shell_keys
        assert "cleanup" not in shell_keys

    def test_quick_reject_yes_persists_decision(self, tmp_path):
        scenario = _load("quick-reject-yes.json")
        run = run_engine_scenario(tmp_path, scenario)

        assert run.final_action["action"] == "completed"
        cp_file = tmp_path / ".workflow-state" / run.final_action["run_id"] / "state.json"
        data = json.loads(cp_file.read_text(encoding="utf-8"))
        result = data["ctx"]["results_scoped"]["final-decision"]
        assert result["output"] == "reject"

    def test_thorough_relay_resume_completes(self, tmp_path):
        scenario = _load("thorough-relay-resume.json")
        run = run_engine_scenario(tmp_path, scenario)

        assert run.final_action["action"] == "completed"
        exec_keys = _exec_keys(run)
        shell_keys = _shell_keys(run)

        for expected in scenario.expect["sequenceContains"]:
            assert expected in exec_keys, f"Missing exec_key {expected} in transcript"

        assert run.restart_events == [{"scope": "relay-child", "exec_key": "session-analyze"}]
        relay_children = run.child_run_ids["llm-session"]
        assert relay_children[0] == relay_children[-1]
        assert len(set(relay_children)) == 1
        assert len(run.child_run_ids["parallel-checks"]) == 3
        assert "finalize" in shell_keys
        assert "cleanup" in shell_keys
