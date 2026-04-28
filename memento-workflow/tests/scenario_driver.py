from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from conftest import create_runner_ns

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class ScenarioStep:
    match: str
    submit: dict[str, Any]
    interactions: list[dict[str, Any]] | None = None


@dataclass
class RestartPoint:
    scope: str
    after_exec_key: str


@dataclass
class Scenario:
    name: str
    workflow: str
    workflow_dirs: list[str]
    variables: dict[str, Any]
    steps: list[ScenarioStep]
    restarts: list[RestartPoint]
    expect: dict[str, Any]


@dataclass
class ScenarioRun:
    final_action: dict[str, Any]
    transcript: list[dict[str, Any]]
    shell_logs: list[dict[str, Any]]
    restart_events: list[dict[str, Any]]
    child_run_ids: dict[str, list[str]]


def load_scenario(path: Path) -> Scenario:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Scenario(
        name=data["name"],
        workflow=data["workflow"],
        workflow_dirs=data.get("workflowDirs", []),
        variables=data.get("variables", {}),
        steps=[ScenarioStep(**step) for step in data.get("steps", [])],
        restarts=[
            RestartPoint(scope=rp["scope"], after_exec_key=rp["afterExecKey"])
            for rp in data.get("restarts", [])
        ],
        expect=data.get("expect", {}),
    )


class ScenarioDriver:
    def __init__(self, tmp_path: Path, scenario: Scenario):
        self.tmp_path = tmp_path
        self.scenario = scenario
        self.ns = create_runner_ns()
        self._start = self.ns["start"]
        self._submit = self.ns["submit"]
        self._next = self.ns["next"]
        self._runs = self.ns["_runs"]
        self.workflow_dirs = [str((_PROJECT_ROOT / p).resolve()) for p in scenario.workflow_dirs]
        self.max_steps = int(scenario.expect.get("maxSteps", 100))
        self.root_run_id = ""
        self.transcript: list[dict[str, Any]] = []
        self.shell_logs: list[dict[str, Any]] = []
        self.restart_events: list[dict[str, Any]] = []
        self.child_run_ids: dict[str, list[str]] = {}
        self._consumed_restarts: set[tuple[str, str]] = set()

    def run(self) -> ScenarioRun:
        action = self._json(
            self._start(
                workflow=self.scenario.workflow,
                cwd=str(self.tmp_path),
                workflow_dirs=self.workflow_dirs,
                variables=self.scenario.variables,
            )
        )
        if action["action"] == "error":
            raise AssertionError(f"Scenario {self.scenario.name} failed to start: {action}")
        self.root_run_id = action["run_id"]
        final_action = self._drive_root(action)
        return ScenarioRun(
            final_action=final_action,
            transcript=self.transcript,
            shell_logs=self.shell_logs,
            restart_events=self.restart_events,
            child_run_ids=self.child_run_ids,
        )

    def _drive_root(self, action: dict[str, Any]) -> dict[str, Any]:
        steps = 0
        self._collect_shell_logs(action)
        while action["action"] not in ("completed", "error", "cancelled"):
            steps += 1
            if steps > self.max_steps:
                raise AssertionError(
                    f"Scenario {self.scenario.name} exceeded {self.max_steps} root steps. "
                    f"Last action: {action}"
                )
            self._record("root", action)

            if action["action"] in ("ask_user", "prompt"):
                submit_payload = self._submit_payload_for(action["exec_key"])
                action = self._json(
                    self._submit(
                        run_id=self.root_run_id,
                        exec_key=action["exec_key"],
                        **submit_payload,
                    )
                )
            elif action["action"] == "subagent":
                self.child_run_ids.setdefault(action["exec_key"], []).append(action["child_run_id"])
                if action.get("relay"):
                    child_result = self._drive_child(action["child_run_id"], scope="relay-child")
                    if child_result.get("_restart_requested"):
                        previous_child = action["child_run_id"]
                        self._runs.clear()
                        action = self._json(
                            self._start(
                                workflow=self.scenario.workflow,
                                cwd=str(self.tmp_path),
                                workflow_dirs=self.workflow_dirs,
                                variables=self.scenario.variables,
                                resume=self.root_run_id,
                            )
                        )
                        self._collect_shell_logs(action)
                        if action["action"] != "subagent":
                            raise AssertionError(
                                f"Expected resumed relay subagent, got {action}"
                            )
                        if action["child_run_id"] != previous_child:
                            raise AssertionError(
                                f"Relay child changed after resume: {previous_child} -> {action['child_run_id']}"
                            )
                        continue
                    if child_result["action"] != "completed":
                        raise AssertionError(f"Relay child did not complete: {child_result}")
                    action = self._json(
                        self._submit(
                            run_id=self.root_run_id,
                            exec_key=action["exec_key"],
                            output=f"relay child {action['child_run_id']} completed",
                        )
                    )
                else:
                    submit_payload = self._submit_payload_for(action["exec_key"])
                    action = self._json(
                        self._submit(
                            run_id=self.root_run_id,
                            exec_key=action["exec_key"],
                            **submit_payload,
                        )
                    )
            elif action["action"] == "parallel":
                self.child_run_ids.setdefault(action["exec_key"], []).extend(
                    lane["child_run_id"] for lane in action["lanes"]
                )
                for lane in action["lanes"]:
                    lane_result = self._drive_child(lane["child_run_id"], scope="parallel-lane")
                    if lane_result["action"] != "completed":
                        raise AssertionError(f"Parallel lane did not complete: {lane_result}")
                action = self._json(
                    self._submit(
                        run_id=self.root_run_id,
                        exec_key=action["exec_key"],
                        output="parallel lanes completed",
                    )
                )
            else:
                raise AssertionError(f"Unhandled root action: {action}")

            self._collect_shell_logs(action)
        return action

    def _drive_child(self, child_run_id: str, *, scope: str) -> dict[str, Any]:
        steps = 0
        action = self._json(self._next(run_id=child_run_id))
        self._collect_shell_logs(action)
        while action["action"] not in ("completed", "error", "cancelled"):
            steps += 1
            if steps > self.max_steps:
                raise AssertionError(
                    f"Scenario {self.scenario.name} exceeded {self.max_steps} child steps. "
                    f"Last child action: {action}"
                )
            self._record(scope, action)
            submitted_exec_key = action["exec_key"]
            submit_payload = self._submit_payload_for(submitted_exec_key)
            action = self._json(
                self._submit(
                    run_id=child_run_id,
                    exec_key=submitted_exec_key,
                    **submit_payload,
                )
            )
            self._collect_shell_logs(action)
            if self._should_restart(scope, submitted_exec_key):
                # restart after the just-submitted exec_key; caller will resume root
                action["_restart_requested"] = True
                return action
        return action

    def _record(self, scope: str, action: dict[str, Any]) -> None:
        self.transcript.append(
            {
                "scope": scope,
                "run_id": action["run_id"],
                "action": action["action"],
                "exec_key": action.get("exec_key", ""),
            }
        )

    def _submit_payload_for(self, exec_key: str) -> dict[str, Any]:
        step = self._find_step(exec_key)
        payload = dict(step.submit)
        payload.setdefault("status", "success")
        return payload

    def _find_step(self, exec_key: str) -> ScenarioStep:
        for step in self.scenario.steps:
            if self._match(step.match, exec_key):
                return step
        raise AssertionError(
            f"Scenario {self.scenario.name} has no canned answer for exec_key '{exec_key}'"
        )

    def _should_restart(self, scope: str, exec_key: str) -> bool:
        for rp in self.scenario.restarts:
            key = (rp.scope, rp.after_exec_key)
            if key in self._consumed_restarts:
                continue
            if rp.scope == scope and rp.after_exec_key == exec_key:
                self._consumed_restarts.add(key)
                self.restart_events.append({"scope": scope, "exec_key": exec_key})
                return True
        return False

    @staticmethod
    def _match(pattern: str, exec_key: str) -> bool:
        regex = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
        return bool(re.match(regex, exec_key))

    def _collect_shell_logs(self, action: dict[str, Any]) -> None:
        self.shell_logs.extend(action.get("_shell_log", []))

    @staticmethod
    def _json(payload: str) -> dict[str, Any]:
        return json.loads(payload)


def run_engine_scenario(tmp_path: Path, scenario: Scenario) -> ScenarioRun:
    return ScenarioDriver(tmp_path, scenario).run()
