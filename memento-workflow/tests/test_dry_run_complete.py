"""Tests for DryRunCompleteAction model and action_to_dict serialization."""

from conftest import _state_ns

action_to_dict = _state_ns["action_to_dict"]


class TestDryRunCompleteAction:
    """Tests for DryRunCompleteAction Pydantic model."""

    def test_model_exists(self):
        """DryRunCompleteAction should be importable from protocol."""
        assert "DryRunCompleteAction" in _state_ns

    def test_action_literal(self):
        """action field should be 'dry_run_complete'."""
        DryRunCompleteAction = _state_ns["DryRunCompleteAction"]
        a = DryRunCompleteAction(
            run_id="r1",
            tree=[],
            summary={
                "step_count": 0,
                "steps_by_type": {},
            },
        )
        assert a.action == "dry_run_complete"

    def test_tree_accepts_dry_run_nodes(self):
        """tree field should accept a list of DryRunNode objects."""
        DryRunCompleteAction = _state_ns["DryRunCompleteAction"]
        DryRunNode = _state_ns["DryRunNode"]
        node = DryRunNode(
            exec_key="step1",
            type="shell",
            name="build",
            detail="npm run build",

            children=[],
        )
        a = DryRunCompleteAction(
            run_id="r1",
            tree=[node],
            summary={
                "step_count": 1,
                "steps_by_type": {"shell": 1},
            },
        )
        assert len(a.tree) == 1
        assert a.tree[0].exec_key == "step1"
        assert a.tree[0].type == "shell"

    def test_nested_children(self):
        """DryRunNode should support nested children."""
        DryRunNode = _state_ns["DryRunNode"]
        DryRunCompleteAction = _state_ns["DryRunCompleteAction"]
        child = DryRunNode(
            exec_key="loop:build[i=0]/compile",
            type="shell",
            name="compile",
            detail="gcc main.c",

            children=[],
        )
        parent = DryRunNode(
            exec_key="loop:build[i=0]",
            type="loop",
            name="build",
            detail="",

            children=[child],
        )
        a = DryRunCompleteAction(
            run_id="r1",
            tree=[parent],
            summary={
                "step_count": 2,
                "steps_by_type": {"shell": 1, "loop": 1},
            },
        )
        assert len(a.tree) == 1
        assert len(a.tree[0].children) == 1
        assert a.tree[0].children[0].exec_key == "loop:build[i=0]/compile"

    def test_summary_fields(self):
        """DryRunSummary should have step_count and steps_by_type."""
        DryRunSummary = _state_ns["DryRunSummary"]
        s = DryRunSummary(step_count=5, steps_by_type={"shell": 3, "prompt": 2})
        assert s.step_count == 5
        assert s.steps_by_type == {"shell": 3, "prompt": 2}


class TestDryRunCompleteActionSerialization:
    """Tests for action_to_dict with DryRunCompleteAction."""

    def test_action_to_dict_basic(self):
        """action_to_dict should serialize DryRunCompleteAction correctly."""
        DryRunCompleteAction = _state_ns["DryRunCompleteAction"]
        DryRunSummary = _state_ns["DryRunSummary"]
        summary = DryRunSummary(
            step_count=0,
            steps_by_type={},
        )
        a = DryRunCompleteAction(run_id="r1", tree=[], summary=summary)
        d = action_to_dict(a)
        assert d["action"] == "dry_run_complete"
        assert d["run_id"] == "r1"
        assert d["tree"] == []
        assert d["summary"]["step_count"] == 0

    def test_action_to_dict_with_nodes(self):
        """action_to_dict should serialize nested tree nodes."""
        DryRunCompleteAction = _state_ns["DryRunCompleteAction"]
        DryRunNode = _state_ns["DryRunNode"]
        DryRunSummary = _state_ns["DryRunSummary"]
        child = DryRunNode(
            exec_key="grp/step1",
            type="prompt",
            name="step1",
            detail="prompt.md",

            children=[],
        )
        parent = DryRunNode(
            exec_key="grp",
            type="group",
            name="grp",
            detail="",

            children=[child],
        )
        summary = DryRunSummary(
            step_count=2,
            steps_by_type={"group": 1, "prompt": 1},
        )
        a = DryRunCompleteAction(run_id="r1", tree=[parent], summary=summary)
        d = action_to_dict(a)
        assert len(d["tree"]) == 1
        assert d["tree"][0]["exec_key"] == "grp"
        assert len(d["tree"][0]["children"]) == 1
        assert d["tree"][0]["children"][0]["name"] == "step1"

    def test_action_to_dict_omits_none(self):
        """action_to_dict should omit None fields."""
        DryRunCompleteAction = _state_ns["DryRunCompleteAction"]
        DryRunSummary = _state_ns["DryRunSummary"]
        summary = DryRunSummary(
            step_count=0,
            steps_by_type={},
        )
        a = DryRunCompleteAction(run_id="r1", tree=[], summary=summary)
        d = action_to_dict(a)
        assert "_shell_log" not in d

    def test_node_type_values(self):
        """DryRunNode type should accept all valid block types."""
        DryRunNode = _state_ns["DryRunNode"]
        valid_types = [
            "shell",
            "llm",
            "prompt",
            "parallel",
            "parallel_each",
            "loop",
            "retry",
            "group",
            "subworkflow",
            "conditional",
        ]
        for t in valid_types:
            node = DryRunNode(exec_key="x", type=t, name="x", detail="", children=[])
            assert node.type == t
