"""Helper sub-workflow for testing SubWorkflow block type.

Echoes injected input back and produces a structured JSON result.
"""

WORKFLOW = WorkflowDef(
    name="test-helper",
    description="Echo injected input back",
    blocks=[
        ShellStep(
            name="helper-echo",
            command="echo '{{variables.helper_input}}'",
        ),
        ShellStep(
            name="helper-transform",
            command="echo '{\"input\": \"{{variables.helper_input}}\", \"done\": true}'",
            result_var="helper_result",
        ),
    ],
)
