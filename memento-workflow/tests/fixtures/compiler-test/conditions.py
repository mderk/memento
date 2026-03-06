"""Condition functions for compiler test workflow."""


def is_thorough(ctx):
    """Check if mode is thorough."""
    return ctx.get_var("variables.mode") == "thorough"


def flaky_succeeded(ctx):
    """Check if flaky command succeeded."""
    result = ctx.get_var("results.flaky-cmd.status")
    return result == "success"
