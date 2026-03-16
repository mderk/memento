"""Analyze the update-environment workflow run ce71e112b6e5 from minerals2.

Reads state.json, artifacts, and children to verify correctness.
"""

import json
from pathlib import Path

import pytest

STATE_DIR = Path("/Users/max/Documents/projects/minerals/minerals2/.workflow-state/ce71e112b6e5")


@pytest.fixture(scope="module")
def state():
    return json.loads((STATE_DIR / "state.json").read_text())


@pytest.fixture(scope="module")
def meta():
    return json.loads((STATE_DIR / "meta.json").read_text())


@pytest.fixture(scope="module")
def variables(state):
    return state["ctx"]["variables"]


@pytest.fixture(scope="module")
def results_scoped(state):
    return state["ctx"]["results_scoped"]


@pytest.fixture(scope="module")
def artifacts():
    arts = {}
    arts_dir = STATE_DIR / "artifacts"
    if not arts_dir.is_dir():
        return arts
    for art_dir in arts_dir.iterdir():
        if not art_dir.is_dir():
            continue
        entry = {}
        for f in art_dir.iterdir():
            if f.is_file() and f.suffix in (".txt", ".json", ".md"):
                entry[f.stem] = f.read_text().strip()
        arts[art_dir.name] = entry
    return arts


@pytest.fixture(scope="module")
def children():
    children_dir = STATE_DIR / "children"
    if not children_dir.is_dir():
        return []
    result = []
    for child_dir in sorted(children_dir.iterdir()):
        if not child_dir.is_dir():
            continue
        sf = child_dir / "state.json"
        if sf.is_file():
            data = json.loads(sf.read_text())
            data["_dir"] = child_dir.name
            result.append(data)
    return result


@pytest.fixture(scope="module")
def child_results(children):
    """All child step results flattened."""
    results = []
    for child in children:
        for key, r in child.get("ctx", {}).get("results_scoped", {}).items():
            results.append({**r, "_child_dir": child["_dir"], "_exec_key": key})
    return results


# ── Meta ──────────────────────────────────────────────────────────────

class TestMeta:
    def test_workflow_name(self, meta):
        assert meta["workflow"] == "update-environment"

    def test_status_completed(self, meta):
        assert meta["status"] == "completed"

    def test_has_timestamps(self, meta):
        assert meta["started_at"]
        assert meta["completed_at"]


# ── Parent steps ──────────────────────────────────────────────────────

class TestParentSteps:
    def test_no_warnings(self, state):
        warnings = state.get("warnings", [])
        assert warnings == [], f"Unexpected warnings: {warnings}"

    def test_all_parent_steps_have_status(self, results_scoped):
        for key, r in results_scoped.items():
            assert "status" in r, f"Missing status for {key}"

    def test_parent_step_statuses(self, results_scoped):
        """Collect all parent step failures (excluding known bugs)."""
        known_bugs = {"fix-links", "redundancy-check"}
        failures = {
            key: r.get("error", r.get("output", "")[:200])
            for key, r in results_scoped.items()
            if r["status"] == "failure" and key not in known_bugs
        }
        assert failures == {}, f"Parent step failures: {failures}"

    def test_known_bug_count(self, results_scoped):
        """Exactly 2 known parent bugs: fix-links and redundancy-check."""
        known_bugs = {"fix-links", "redundancy-check"}
        actual_bugs = {
            key for key, r in results_scoped.items()
            if r["status"] == "failure" and key in known_bugs
        }
        assert actual_bugs == known_bugs


# ── Variables ─────────────────────────────────────────────────────────

class TestVariables:
    def test_has_plugin_root(self, variables):
        assert "plugin_root" in variables

    def test_has_pre_update(self, variables):
        assert "pre_update" in variables

    def test_has_generation_plan(self, variables):
        assert "generation_plan" in variables

    def test_generation_plan_has_prompt_items(self, variables):
        plan = variables.get("generation_plan", {})
        assert "prompt_items" in plan, f"generation_plan keys: {list(plan.keys())}"
        assert isinstance(plan["prompt_items"], list)
        assert len(plan["prompt_items"]) > 0

    def test_has_context_check(self, variables):
        assert variables.get("context_check", {}).get("exists") is True


# ── Artifact errors ───────────────────────────────────────────────────

class TestArtifacts:
    def test_fix_links_error(self, artifacts):
        """BUG: fix-links passes --memory-bank but script expects --files or no args."""
        art = artifacts.get("fix-links", {})
        assert "error" in art, "Expected fix-links to have error artifact"
        assert "--memory-bank" in art.get("command", "") or "--memory-bank" in art.get("error", "")

    def test_redundancy_check_error(self, artifacts):
        """BUG: redundancy-check passes --memory-bank but script expects positional arg."""
        art = artifacts.get("redundancy-check", {})
        assert "error" in art, "Expected redundancy-check to have error artifact"

    def test_no_other_artifact_errors(self, artifacts):
        """No artifacts besides fix-links and redundancy-check should have errors."""
        known_errors = {"fix-links", "redundancy-check"}
        unexpected = {
            name: art["error"][:200]
            for name, art in artifacts.items()
            if "error" in art and name not in known_errors
        }
        assert unexpected == {}, f"Unexpected artifact errors: {unexpected}"


# ── Children (parallel regenerate-files) ──────────────────────────────

class TestChildren:
    def test_has_children(self, children):
        assert len(children) > 0

    def test_all_children_completed(self, children):
        not_completed = [
            (c["_dir"], c.get("status"))
            for c in children
            if c.get("status") != "completed"
        ]
        assert not_completed == [], f"Children not completed: {not_completed}"

    def test_merge_file_failures(self, child_results):
        """BUG: merge-file fails because --base-commit is missing from the command."""
        merge_failures = [
            r["_exec_key"]
            for r in child_results
            if r.get("name") == "merge-file" and r.get("status") == "failure"
        ]
        # All merge-file steps should have failed (known bug)
        assert len(merge_failures) > 0, "Expected merge-file failures (--base-commit bug)"

    def test_merge_file_error_message(self, child_results):
        """Verify the error is specifically about --base-commit."""
        for r in child_results:
            if r.get("name") == "merge-file" and r.get("status") == "failure":
                error = r.get("error", "")
                assert "base-commit" in error.lower() or "base_commit" in error.lower(), (
                    f"Unexpected merge-file error: {error[:200]}"
                )

    def test_generate_file_all_succeeded(self, child_results):
        """All generate-file LLM steps should have succeeded."""
        gen_failures = [
            (r["_exec_key"], r.get("error", "")[:100])
            for r in child_results
            if r.get("name") == "generate-file" and r.get("status") != "success"
        ]
        assert gen_failures == [], f"generate-file failures: {gen_failures}"

    def test_no_unknown_child_failures(self, child_results):
        """No child steps besides merge-file should have failed."""
        other_failures = [
            (r["_exec_key"], r.get("name"), r.get("error", "")[:100])
            for r in child_results
            if r.get("status") == "failure" and r.get("name") != "merge-file"
        ]
        assert other_failures == [], f"Unexpected child failures: {other_failures}"


# ── Workflow definition vs script interfaces ──────────────────────────

PLUGIN_ROOT = Path("/Users/max/Documents/projects/memento/memento")


class TestWorkflowScriptInterfaces:
    """Verify that workflow.py commands match actual script CLI interfaces."""

    def test_validate_links_accepts_no_args(self):
        """validate-memory-bank-links.py should work with no args (full scan)."""
        import subprocess
        script = PLUGIN_ROOT / "skills/fix-broken-links/scripts/validate-memory-bank-links.py"
        # Just check --help to verify interface
        r = subprocess.run(
            ["python3", str(script), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert r.returncode == 0
        # Script accepts --files, NOT --memory-bank
        assert "--files" in r.stdout
        assert "--memory-bank" not in r.stdout

    def test_check_redundancy_accepts_positional(self):
        """check-redundancy.py expects a positional file arg, not --memory-bank."""
        import subprocess
        script = PLUGIN_ROOT / "skills/check-redundancy/scripts/check-redundancy.py"
        r = subprocess.run(
            ["python3", str(script)],
            capture_output=True, text=True, timeout=10,
        )
        # With no args it prints usage to stderr
        assert "Usage:" in r.stderr or "usage:" in r.stderr.lower()
        assert "--memory-bank" not in r.stderr

    def test_merge_requires_base_commit(self):
        """analyze.py merge requires --base-commit."""
        import subprocess
        script = PLUGIN_ROOT / "skills/analyze-local-changes/scripts/analyze.py"
        r = subprocess.run(
            ["python3", str(script), "merge", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert r.returncode == 0
        assert "--base-commit" in r.stdout

    def test_workflow_merge_command_has_base_commit(self):
        """merge-file command must include --base-commit."""
        wf_path = PLUGIN_ROOT / "skills/update-environment/workflow.py"
        source = wf_path.read_text()
        assert "--base-commit" in source

    def test_workflow_fix_links_no_memory_bank_arg(self):
        """fix-links must NOT pass --memory-bank (script doesn't accept it)."""
        wf_path = PLUGIN_ROOT / "skills/update-environment/workflow.py"
        source = wf_path.read_text()
        # Find the fix-links command line specifically
        lines = source.split("\n")
        for i, line in enumerate(lines):
            if "validate-memory-bank-links" in line:
                # The command should NOT have --memory-bank
                cmd_lines = line
                if i + 1 < len(lines) and '",\n' not in line:
                    cmd_lines += lines[i + 1]
                assert "--memory-bank" not in cmd_lines

    def test_workflow_redundancy_check_positional_arg(self):
        """redundancy-check must pass a positional file path, not --memory-bank."""
        wf_path = PLUGIN_ROOT / "skills/update-environment/workflow.py"
        source = wf_path.read_text()
        assert "--memory-bank" not in source.split("check-redundancy.py")[1].split("ShellStep")[0]
        # The full command (may span multiple lines) should reference .memory_bank
        assert ".memory_bank" in source.split("check-redundancy.py")[1].split("ShellStep")[0]

    def test_pre_update_returns_base_commit(self):
        """cmd_pre_update must include base_commit in its result."""
        script = PLUGIN_ROOT / "skills/analyze-local-changes/scripts/analyze.py"
        # Just check the source contains base_commit in the return dict
        source = script.read_text()
        assert "'base_commit'" in source or '"base_commit"' in source
        # Verify it's in cmd_pre_update specifically
        in_pre_update = False
        for line in source.split("\n"):
            if "def cmd_pre_update" in line:
                in_pre_update = True
            if in_pre_update and "base_commit" in line:
                break
        else:
            pytest.fail("base_commit not found in cmd_pre_update")
