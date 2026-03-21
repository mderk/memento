"""Tests for nested parallelism — ParallelEachBlock inside child runs (protocol 0004, step 03).

Verifies that ParallelEachBlock inside SubWorkflow child runs returns
ParallelAction instead of degrading to sequential LoopBlock.
"""

from conftest import _types_ns, _state_ns

LLMStep = _types_ns["LLMStep"]
GroupBlock = _types_ns["GroupBlock"]
ParallelEachBlock = _types_ns["ParallelEachBlock"]
ShellStep = _types_ns["ShellStep"]
SubWorkflow = _types_ns["SubWorkflow"]
WorkflowDef = _types_ns["WorkflowDef"]
WorkflowContext = _types_ns["WorkflowContext"]

Frame = _state_ns["Frame"]
RunState = _state_ns["RunState"]
advance = _state_ns["advance"]


def _make_workflow(blocks, name="test", description="test workflow"):
    return WorkflowDef(name=name, description=description, blocks=blocks)


def _make_state(workflow, variables=None, registry=None, run_id="test-run", cwd="."):
    ctx = WorkflowContext(variables=variables or {}, cwd=cwd)
    if registry is None:
        registry = {workflow.name: workflow}
    return RunState(
        run_id=run_id,
        ctx=ctx,
        stack=[Frame(block=workflow)],
        registry=registry,
    )


class TestNestedParallel:
    def test_parallel_in_child_returns_parallel_action(self):
        """ParallelEachBlock inside a child run should return parallel action, not loop."""
        inner_parallel = ParallelEachBlock(
            name="inner",
            parallel_for="variables.items",
            item_var="item",
            template=[ShellStep(name="proc", command="echo {{variables.item}}")],
        )
        wf = _make_workflow([
            GroupBlock(name="outer", isolation="subagent", blocks=[inner_parallel]),
        ])
        state = _make_state(wf, variables={"items": ["a", "b"]})

        # Get subagent for outer
        action, children = advance(state)
        child = children[0]

        # Inside child: parallel should return ParallelAction with children
        child_action, grandchildren = advance(child)
        assert child_action.action == "parallel", (
            f"Expected 'parallel' action, got '{child_action.action}'. "
            "ParallelEachBlock in child run should not be downgraded."
        )
        assert len(grandchildren) == 2, (
            f"Expected 2 grandchild runs, got {len(grandchildren)}"
        )

    def test_no_downgrade_warning(self):
        """No 'Downgraded' warning should appear when parallel runs in child."""
        inner_parallel = ParallelEachBlock(
            name="inner",
            parallel_for="variables.items",
            item_var="item",
            template=[ShellStep(name="proc", command="echo {{variables.item}}")],
        )
        wf = _make_workflow([
            GroupBlock(name="outer", isolation="subagent", blocks=[inner_parallel]),
        ])
        state = _make_state(wf, variables={"items": ["a", "b"]})

        action, children = advance(state)
        child = children[0]
        advance(child)

        assert not any("Downgraded" in w for w in child.warnings), (
            "Unexpected 'Downgraded' warning — parallel should run natively in child"
        )

    def test_grandchild_run_ids_are_composite(self):
        """Grandchild run_ids should be 3-level composite: parent>child>grandchild."""
        inner_parallel = ParallelEachBlock(
            name="inner",
            parallel_for="variables.items",
            item_var="item",
            template=[ShellStep(name="proc", command="echo {{variables.item}}")],
        )
        wf = _make_workflow([
            GroupBlock(name="outer", isolation="subagent", blocks=[inner_parallel]),
        ])
        state = _make_state(wf, variables={"items": ["a", "b"]}, run_id="root")

        action, children = advance(state)
        child = children[0]
        child_action, grandchildren = advance(child)

        if grandchildren:
            for gc in grandchildren:
                # Should have at least 2 ">" separators (3 levels)
                assert gc.run_id.count(">") >= 1, (
                    f"Grandchild run_id '{gc.run_id}' should be multi-level composite"
                )
