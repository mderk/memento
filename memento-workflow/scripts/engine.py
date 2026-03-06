"""Workflow engine utilities.

Kept for backward compatibility and shared helpers used by both
the state machine (state.py) and the MCP runner (runner.py).

The async execute_* functions have been replaced by the state machine
in state.py. This module re-exports key functions from state.py and
provides additional utilities.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, Literal

from .types import (
    Block,
    ConditionalBlock,
    GroupBlock,
    LLMStep,
    LoopBlock,
    ParallelEachBlock,
    PromptStep,
    RetryBlock,
    ShellStep,
    StepResult,
    SubWorkflow,
    WorkflowContext,
    WorkflowDef,
)

# Re-export from state.py (canonical implementations)
from .state import (
    evaluate_condition,
    load_prompt,
    record_leaf_result as _record_leaf_result,
    results_key as _results_key,
    schema_dict as _schema_dict,
    substitute as _substitute,
    validate_structured_output as _parse_structured_output_v2,
    dry_run_structured_output as _dry_run_structured_output,
    workflow_hash,
    PROTOCOL_VERSION,
)


# ---------------------------------------------------------------------------
# Progress feedback
# ---------------------------------------------------------------------------

logger = logging.getLogger("workflow-engine")


def _emit(ctx: WorkflowContext, message: str) -> None:
    """Print an indented progress line based on current scope depth."""
    depth = len(getattr(ctx, "_scope", []))
    indent = "  " * (depth + 1)
    print(f"{indent}{message}")
