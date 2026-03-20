"""Tests for dashboard data layer, app factory, and CLI.

Uses a temporary .workflow-state/ fixture directory to test
list_runs, get_run_detail, get_artifact_content, diff_runs,
the Starlette app factory, and the CLI output.
"""

import json
import subprocess
import sys
from pathlib import Path
import pytest

# dashboard/ is a subpackage of memento-workflow, not an installed package
WORKFLOW_ROOT = Path(__file__).resolve().parent.parent
if str(WORKFLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKFLOW_ROOT))

from dashboard.data import (  # noqa: E402
    diff_runs,
    get_artifact_content,
    get_run_detail,
    list_runs,
)


# ── Fixtures ──


@pytest.fixture
def state_dir(tmp_path):
    """Create a realistic .workflow-state/ directory structure."""
    sd = tmp_path / ".workflow-state"

    # Run 1: completed, with steps and artifacts
    r1 = sd / "aaa111aaa111"
    (r1 / "artifacts" / "step-one").mkdir(parents=True)
    (r1 / "artifacts" / "step-one" / "output.txt").write_text("hello world")
    (r1 / "artifacts" / "step-one" / "result.json").write_text('{"ok": true}')
    (r1 / "artifacts" / "step-two").mkdir(parents=True)
    (r1 / "artifacts" / "step-two" / "output.txt").write_text("step two out")

    r1_meta = {
        "run_id": "aaa111aaa111",
        "workflow": "test-workflow",
        "cwd": str(tmp_path),
        "status": "completed",
        "started_at": "2026-03-01T10:00:00+00:00",
        "completed_at": "2026-03-01T10:05:00+00:00",
    }
    (r1 / "meta.json").write_text(json.dumps(r1_meta))

    r1_state = {
        "run_id": "aaa111aaa111",
        "status": "completed",
        "parent_run_id": None,
        "child_run_ids": ["ccc333ccc333"],
        "ctx": {
            "results_scoped": {
                "step-one": {
                    "results_key": "step-one",
                    "name": "Step One",
                    "status": "success",
                    "output": "hello world",
                    "duration": 1.5,
                    "error": None,
                    "cost_usd": 0.01,
                    "order": 1,
                },
                "step-two": {
                    "results_key": "step-two",
                    "name": "Step Two",
                    "status": "success",
                    "output": "step two out",
                    "duration": 0.3,
                    "error": None,
                    "cost_usd": None,
                    "order": 2,
                },
            }
        },
    }
    (r1 / "state.json").write_text(json.dumps(r1_state))

    # Child run under run 1
    child = r1 / "children" / "ccc333ccc333"
    (child / "artifacts" / "par-batch-child-step" / "i-0" / "par-do-thing" / "i-0" / "do-thing").mkdir(parents=True)
    (child / "artifacts" / "par-batch-child-step" / "i-0" / "par-do-thing" / "i-0" / "do-thing" / "output.txt").write_text(
        "child output"
    )

    child_meta = {
        "run_id": "ccc333ccc333",
        "workflow": "",
        "cwd": str(tmp_path),
        "status": "completed",
        "started_at": "2026-03-01T10:01:00+00:00",
        "completed_at": "2026-03-01T10:03:00+00:00",
    }
    (child / "meta.json").write_text(json.dumps(child_meta))

    # Child state inherits parent's steps + has its own
    child_state = {
        "run_id": "ccc333ccc333",
        "parent_run_id": "aaa111aaa111",
        "status": "completed",
        "child_run_ids": [],
        "parallel_block_name": "child-step",
        "lane_index": 0,
        "ctx": {
            "results_scoped": {
                # Inherited from parent
                "step-one": {
                    "results_key": "step-one",
                    "name": "Step One",
                    "status": "success",
                    "output": "hello world",
                    "duration": 1.5,
                    "error": None,
                    "cost_usd": 0.01,
                    "order": 1,
                },
                "step-two": {
                    "results_key": "step-two",
                    "name": "Step Two",
                    "status": "success",
                    "output": "step two out",
                    "duration": 0.3,
                    "error": None,
                    "cost_usd": None,
                    "order": 2,
                },
                # Child's own step
                "par-batch:child-step[i=0]/par:do-thing[i=0]/do-thing": {
                    "results_key": "do-thing",
                    "name": "Do Thing",
                    "status": "success",
                    "output": "child output",
                    "duration": 2.0,
                    "error": None,
                    "cost_usd": 0.05,
                    "order": 3,
                },
            }
        },
    }
    (child / "state.json").write_text(json.dumps(child_state))

    # Run 2: error, different artifacts for diffing
    r2 = sd / "bbb222bbb222"
    (r2 / "artifacts" / "step-one").mkdir(parents=True)
    (r2 / "artifacts" / "step-one" / "output.txt").write_text("different output")
    (r2 / "artifacts" / "step-one" / "result.json").write_text('{"ok": false}')

    r2_meta = {
        "run_id": "bbb222bbb222",
        "workflow": "test-workflow",
        "cwd": str(tmp_path),
        "status": "error",
        "started_at": "2026-03-02T10:00:00+00:00",
        "completed_at": "2026-03-02T10:02:00+00:00",
    }
    (r2 / "meta.json").write_text(json.dumps(r2_meta))

    r2_state = {
        "run_id": "bbb222bbb222",
        "status": "error",
        "parent_run_id": None,
        "child_run_ids": [],
        "ctx": {
            "results_scoped": {
                "step-one": {
                    "results_key": "step-one",
                    "name": "Step One",
                    "status": "failure",
                    "output": "different output",
                    "duration": 0.8,
                    "error": "something broke",
                    "cost_usd": 0.02,
                    "order": 1,
                },
            }
        },
    }
    (r2 / "state.json").write_text(json.dumps(r2_state))

    return sd


# ── Data layer tests ──


class TestListRuns:
    def test_lists_top_level_runs(self, state_dir):
        runs = list_runs(state_dir)
        ids = [r["run_id"] for r in runs]
        assert "aaa111aaa111" in ids
        assert "bbb222bbb222" in ids

    def test_includes_children(self, state_dir):
        runs = list_runs(state_dir)
        parent = next(r for r in runs if r["run_id"] == "aaa111aaa111")
        assert len(parent["children"]) == 1
        assert parent["children"][0]["run_id"] == "ccc333ccc333"

    def test_empty_dir(self, tmp_path):
        assert list_runs(tmp_path / "nonexistent") == []


class TestGetRunDetail:
    def test_returns_steps_with_artifacts(self, state_dir):
        detail = get_run_detail(state_dir, "aaa111aaa111")
        assert detail is not None
        assert detail["meta"]["workflow"] == "test-workflow"
        assert detail["meta"]["status"] == "completed"
        assert len(detail["steps"]) == 2

        s1 = detail["steps"][0]
        assert s1["name"] == "Step One"
        assert s1["order"] == 1
        assert "output.txt" in s1["artifact_files"]
        assert "result.json" in s1["artifact_files"]

    def test_child_excludes_parent_steps(self, state_dir):
        detail = get_run_detail(state_dir, "ccc333ccc333")
        assert detail is not None
        # Should only have the child's own step, not the 2 inherited parent steps
        assert len(detail["steps"]) == 1
        assert detail["steps"][0]["name"] == "Do Thing"

    def test_not_found(self, state_dir):
        assert get_run_detail(state_dir, "nonexistent") is None

    def test_step_ordering(self, state_dir):
        detail = get_run_detail(state_dir, "aaa111aaa111")
        assert detail is not None
        orders = [s["order"] for s in detail["steps"]]
        assert orders == sorted(orders)


class TestGetArtifactContent:
    def test_reads_file(self, state_dir):
        content = get_artifact_content(state_dir, "aaa111aaa111", "step-one/output.txt")
        assert content == "hello world"

    def test_not_found(self, state_dir):
        assert get_artifact_content(state_dir, "aaa111aaa111", "nonexistent") is None

    def test_child_artifact(self, state_dir):
        content = get_artifact_content(
            state_dir, "ccc333ccc333",
            "par-batch-child-step/i-0/par-do-thing/i-0/do-thing/output.txt",
        )
        assert content == "child output"

    def test_path_traversal_blocked(self, state_dir):
        assert get_artifact_content(state_dir, "aaa111aaa111", "../../meta.json") is None


class TestDiffRuns:
    def test_detects_modified_step(self, state_dir):
        result = diff_runs(state_dir, "aaa111aaa111", "bbb222bbb222")
        assert result is not None
        diffs = result["diffs"]
        # step-one exists in both, step-two only in run 1
        step_one = next(d for d in diffs if d["results_key"] == "step-one")
        assert step_one["change"] == "modified"
        assert len(step_one["artifact_diffs"]) > 0

    def test_detects_removed_step(self, state_dir):
        result = diff_runs(state_dir, "aaa111aaa111", "bbb222bbb222")
        assert result is not None
        step_two = next(d for d in result["diffs"] if d["results_key"] == "step-two")
        assert step_two["change"] == "removed"

    def test_not_found(self, state_dir):
        assert diff_runs(state_dir, "aaa111aaa111", "nonexistent") is None


# ── CLI tests ──


def _run_cli(*args: str, cwd: str = ".") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "dashboard.cli", "--cwd", cwd, *args],
        capture_output=True,
        text=True,
        cwd=str(WORKFLOW_ROOT),
    )


class TestCLI:
    def test_runs_command(self, state_dir):
        r = _run_cli("runs", cwd=str(state_dir.parent))
        assert r.returncode == 0
        assert "aaa111aa" in r.stdout
        assert "bbb222bb" in r.stdout
        assert "test-workflow" in r.stdout

    def test_run_detail(self, state_dir):
        r = _run_cli("run", "aaa111aaa111", cwd=str(state_dir.parent))
        assert r.returncode == 0
        assert "step-one" in r.stdout
        assert "step-two" in r.stdout
        assert "output.txt" in r.stdout

    def test_run_prefix_match(self, state_dir):
        r = _run_cli("run", "aaa1", cwd=str(state_dir.parent))
        assert r.returncode == 0
        assert "aaa111aaa111" in r.stdout

    def test_child_run_excludes_parent_steps(self, state_dir):
        r = _run_cli("run", "ccc333ccc333", cwd=str(state_dir.parent))
        assert r.returncode == 0
        assert "do-thing" in r.stdout
        # Should NOT contain parent-only steps
        assert "step-one" not in r.stdout
        assert "step-two" not in r.stdout

    def test_artifact_command(self, state_dir):
        r = _run_cli(
            "artifact", "aaa111aaa111", "step-one/output.txt",
            cwd=str(state_dir.parent),
        )
        assert r.returncode == 0
        assert r.stdout == "hello world"

    def test_steps_json(self, state_dir):
        r = _run_cli("steps", "aaa111aaa111", cwd=str(state_dir.parent))
        assert r.returncode == 0
        steps = json.loads(r.stdout)
        assert len(steps) == 2
        assert steps[0]["name"] == "Step One"

    def test_diff_command(self, state_dir):
        r = _run_cli("diff", "aaa111aaa111", "bbb222bbb222", cwd=str(state_dir.parent))
        assert r.returncode == 0
        assert "modified" in r.stdout
        assert "removed" in r.stdout

    def test_not_found(self, state_dir):
        r = _run_cli("run", "zzz_nonexistent", cwd=str(state_dir.parent))
        assert r.returncode != 0

    def test_no_command(self, state_dir):
        r = _run_cli(cwd=str(state_dir.parent))
        assert r.returncode != 0


# ── App factory tests ──

from dashboard.app import _SPAStaticFiles, create_app  # noqa: E402


class TestCreateApp:
    def test_returns_starlette_app(self, tmp_path):
        from starlette.applications import Starlette

        app = create_app(str(tmp_path))
        assert isinstance(app, Starlette)

    def test_state_dir_set(self, tmp_path):
        app = create_app(str(tmp_path))
        assert app.state.state_dir == tmp_path.resolve() / ".workflow-state"

    def test_cwd_set(self, tmp_path):
        app = create_app(str(tmp_path))
        assert app.state.cwd == str(tmp_path.resolve())

    def test_includes_api_routes(self, tmp_path):
        app = create_app(str(tmp_path))
        # Collect all route paths from the app
        route_paths = set()
        for route in app.routes:
            path = getattr(route, "path", None)
            if path is not None:
                route_paths.add(path)
        # Verify known API paths exist
        assert "/api/info" in route_paths
        assert "/api/runs" in route_paths
        assert "/api/runs/{run_id}" in route_paths
        assert "/api/runs/{run_id}/artifacts/{path:path}" in route_paths
        assert "/api/diff/{id1}/{id2}" in route_paths
        assert "/api/shutdown" in route_paths
        assert "/api/ws" in route_paths


class TestSPAStaticFiles:
    @pytest.fixture
    def spa_dir(self, tmp_path):
        """Create a minimal SPA directory with index.html."""
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<html><body>SPA</body></html>")
        (dist / "style.css").write_text("body { color: red; }")
        return dist

    def test_serves_existing_file(self, spa_dir):
        from starlette.testclient import TestClient
        from starlette.applications import Starlette
        from starlette.routing import Mount

        app = Starlette(routes=[
            Mount("/", app=_SPAStaticFiles(directory=str(spa_dir), html=True)),
        ])
        client = TestClient(app)
        resp = client.get("/style.css")
        assert resp.status_code == 200
        assert "color: red" in resp.text

    def test_falls_back_to_index_html(self, spa_dir):
        from starlette.testclient import TestClient
        from starlette.applications import Starlette
        from starlette.routing import Mount

        app = Starlette(routes=[
            Mount("/", app=_SPAStaticFiles(directory=str(spa_dir), html=True)),
        ])
        client = TestClient(app)
        resp = client.get("/nonexistent/route")
        assert resp.status_code == 200
        assert "SPA" in resp.text


# ============ CORS restriction ============


class TestDashboardCORS:
    """CORS should restrict methods and headers."""

    def test_cors_methods_restricted(self):
        from dashboard.app import create_app
        from starlette.testclient import TestClient as _TC

        app = create_app("/tmp")
        client = _TC(app)

        resp = client.options(
            "/api/info",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "DELETE",
            },
        )
        allowed = resp.headers.get("access-control-allow-methods", "")
        assert "DELETE" not in allowed, f"CORS should not allow DELETE, got: {allowed}"


# ============ Dashboard helpers ============


class TestDashboardHelpers:
    """Tests for check_existing_dashboard, save_dashboard_lock."""

    def test_check_existing_no_lock_file(self, tmp_path):
        from scripts.infra.dashboard_helpers import check_existing_dashboard
        result = check_existing_dashboard(str(tmp_path))
        assert result is None

    def test_check_existing_corrupt_lock_file(self, tmp_path):
        from scripts.infra.dashboard_helpers import check_existing_dashboard
        lock_dir = tmp_path / ".workflow-state"
        lock_dir.mkdir()
        lock_file = lock_dir / ".dashboard.json"
        lock_file.write_text("not json")

        result = check_existing_dashboard(str(tmp_path))
        assert result is None
        assert not lock_file.exists()

    def test_check_existing_stale_pid(self, tmp_path):
        from scripts.infra.dashboard_helpers import check_existing_dashboard
        lock_dir = tmp_path / ".workflow-state"
        lock_dir.mkdir()
        lock_file = lock_dir / ".dashboard.json"
        lock_file.write_text(
            json.dumps({"url": "http://localhost:9999", "pid": 999999999})
        )

        result = check_existing_dashboard(str(tmp_path))
        assert result is None
        assert not lock_file.exists()

    def test_save_dashboard_lock_creates_file(self, tmp_path):
        from scripts.infra.dashboard_helpers import save_dashboard_lock
        save_dashboard_lock(str(tmp_path), "http://localhost:8080", 12345)

        lock_file = tmp_path / ".workflow-state" / ".dashboard.json"
        assert lock_file.exists()
        data = json.loads(lock_file.read_text())
        assert data["url"] == "http://localhost:8080"
        assert data["pid"] == 12345

    def test_save_dashboard_lock_creates_parent_dir(self, tmp_path):
        from scripts.infra.dashboard_helpers import save_dashboard_lock
        cwd = tmp_path / "newproject"
        cwd.mkdir()
        save_dashboard_lock(str(cwd), "http://localhost:8080", 12345)

        lock_file = cwd / ".workflow-state" / ".dashboard.json"
        assert lock_file.exists()

    def test_check_existing_empty_url(self, tmp_path):
        from scripts.infra.dashboard_helpers import check_existing_dashboard
        lock_dir = tmp_path / ".workflow-state"
        lock_dir.mkdir()
        lock_file = lock_dir / ".dashboard.json"
        lock_file.write_text(json.dumps({"url": "", "pid": 12345}))

        result = check_existing_dashboard(str(tmp_path))
        assert result is None
