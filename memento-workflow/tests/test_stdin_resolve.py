"""Tests for stdin template resolution (Fix J).

Verifies that _resolve_stdin strips {{}} wrappers from stdin dotpaths
so that runner.py's get_var() receives bare dotpaths.
"""

from conftest import _state_ns, _types_ns

_resolve_stdin = _state_ns["_resolve_stdin"]
_build_shell_action = _state_ns["_build_shell_action"]
RunState = _state_ns["RunState"]
Frame = _state_ns["Frame"]
ShellStep = _types_ns["ShellStep"]
WorkflowDef = _types_ns["WorkflowDef"]
WorkflowContext = _types_ns["WorkflowContext"]


class TestResolveStdin:
    """Unit tests for _resolve_stdin helper."""

    def test_template_syntax_stripped(self):
        """{{results.foo.structured_output}} → results.foo.structured_output"""
        assert _resolve_stdin("{{results.foo.structured_output}}") == "results.foo.structured_output"

    def test_template_with_spaces_stripped(self):
        """{{ results.foo.output }} → results.foo.output"""
        assert _resolve_stdin("{{ results.foo.output }}") == "results.foo.output"

    def test_bare_dotpath_unchanged(self):
        """results.foo.output passes through as-is."""
        assert _resolve_stdin("results.foo.output") == "results.foo.output"

    def test_empty_string_returns_none(self):
        assert _resolve_stdin("") is None

    def test_none_like_empty_returns_none(self):
        assert _resolve_stdin("   ") is None

    def test_single_braces_not_stripped(self):
        """{not_a_template} should not be stripped."""
        assert _resolve_stdin("{not_a_template}") == "{not_a_template}"

    def test_nested_braces_only_outer_stripped(self):
        """{{variables.data}} — standard case."""
        assert _resolve_stdin("{{variables.data}}") == "variables.data"

    def test_unclosed_template_not_stripped(self):
        """{{unclosed is not a valid template — pass through as-is."""
        assert _resolve_stdin("{{unclosed") == "{{unclosed"

    def test_mismatched_braces_not_stripped(self):
        """}}reversed{{ is not a valid template."""
        assert _resolve_stdin("}}reversed{{") == "}}reversed{{"


class TestBuildShellActionStdin:
    """Integration: _build_shell_action passes resolved stdin to ShellAction."""

    def _make_state(self, variables=None):
        wf = WorkflowDef(name="test", description="test")
        ctx = WorkflowContext(variables=variables or {}, cwd=".")
        return RunState(
            run_id="test-run",
            ctx=ctx,
            stack=[Frame(block=wf)],
            registry={"test": wf},
        )

    def test_stdin_template_resolved_in_action(self):
        """ShellStep with stdin='{{results.foo.output}}' produces bare dotpath in action."""
        state = self._make_state()
        step = ShellStep(name="test-shell", command="cat", stdin="{{results.foo.output}}")
        action = _build_shell_action(state, step, "test-shell")
        assert action.stdin == "results.foo.output"

    def test_stdin_bare_dotpath_in_action(self):
        """ShellStep with bare stdin dotpath passes through."""
        state = self._make_state()
        step = ShellStep(name="test-shell", command="cat", stdin="results.bar.output")
        action = _build_shell_action(state, step, "test-shell")
        assert action.stdin == "results.bar.output"

    def test_no_stdin_produces_none(self):
        """ShellStep without stdin has None in action."""
        state = self._make_state()
        step = ShellStep(name="test-shell", command="echo hi")
        action = _build_shell_action(state, step, "test-shell")
        assert action.stdin is None
