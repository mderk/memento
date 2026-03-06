# pyright: reportUndefinedVariable=false

WORKFLOW = WorkflowDef(
    name="ask-user-e2e",
    description="E2E ask_user test",
    blocks=[
        LLMStep(
            name="choose",
            prompt="ask.md",
            tools=["ask_user"],
            model="sonnet",
        )
    ],
)
