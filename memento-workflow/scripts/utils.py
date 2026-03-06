"""Pure utility functions for the workflow engine.

Template substitution, condition evaluation, result recording,
schema helpers, and workflow hashing.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

from .types import (
    StepResult,
    WorkflowContext,
    WorkflowDef,
)

import logging

logger = logging.getLogger("workflow-engine")

_VAR_RE = re.compile(r"\{\{([\w.\-]+)\}\}")


# ---------------------------------------------------------------------------
# Template substitution (extracted from engine.py)
# ---------------------------------------------------------------------------


def substitute(template: str, ctx: WorkflowContext) -> str:
    """Replace {{results.X}} and {{variables.X}} in a string."""

    def _replace(m: re.Match) -> str:
        val = ctx.get_var(m.group(1))
        if val is None:
            return m.group(0)  # leave unresolved
        if isinstance(val, (dict, list)):
            return json.dumps(val, indent=2)
        return str(val)

    return _VAR_RE.sub(_replace, template)


def load_prompt(path: str, ctx: WorkflowContext) -> str:
    """Read a prompt file and substitute template variables."""
    full = Path(ctx.prompt_dir) / path
    logger.debug("load_prompt: %s (prompt_dir=%s)", full, ctx.prompt_dir)
    text = full.read_text(encoding="utf-8")
    return substitute(text, ctx)


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------


def evaluate_condition(
    cond: Callable[[WorkflowContext], bool] | None,
    ctx: WorkflowContext,
) -> bool:
    """Call a condition callable, or return True if None."""
    if cond is None:
        return True
    try:
        return cond(ctx)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Result identity helpers (extracted from engine.py)
# ---------------------------------------------------------------------------


def results_key(ctx: WorkflowContext, base: str) -> str:
    """Convenience key for ctx.results: dot-prefix subworkflow stack only."""
    subs: list[str] = []
    for part in getattr(ctx, "_scope", []):
        if part.startswith("sub:"):
            subs.append(part.removeprefix("sub:"))
    if subs:
        return ".".join([*subs, base])
    return base


def record_leaf_result(
    ctx: WorkflowContext,
    base: str,
    result: StepResult,
    *,
    update_last: bool = True,
    order: int | None = None,
) -> StepResult:
    """Record a leaf StepResult into scoped + convenience stores."""
    if not result.exec_key:
        result.exec_key = ctx.scoped_exec_key(base)
    result.base = base
    result.results_key = results_key(ctx, base)
    if order is None:
        result.order = ctx.next_order()
    else:
        result.order = order
    ctx.results_scoped[result.exec_key] = result
    if update_last:
        ctx.results[result.results_key] = result
    return result


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------


def schema_dict(model: type | None) -> dict[str, Any] | None:
    """Convert a Pydantic model class to a JSON Schema dict."""
    if model is None:
        return None
    return model.model_json_schema()


def validate_structured_output(
    output: str | None,
    structured_output: dict | None,
    output_schema: Any,
) -> tuple[Any, str | None]:
    """Validate structured output against schema.

    Returns (validated_output, error_message).
    """
    if output_schema is None:
        return structured_output, None

    data = structured_output
    if data is None and output:
        try:
            data = json.loads(output)
        except (json.JSONDecodeError, ValueError):
            return None, f"Output is not valid JSON: {output[:200]}"

    if data is None:
        return None, "No structured output provided and output is not JSON"

    try:
        if hasattr(output_schema, "model_validate"):
            validated = output_schema.model_validate(data).model_dump()
            return validated, None
    except Exception as exc:
        return None, f"Schema validation failed: {exc}"

    return data, None


def dry_run_structured_output(model: Any) -> Any:
    """Generate minimal structured output for dry-runs."""
    if model is None:
        return None
    if not hasattr(model, "model_fields"):
        return None

    try:
        from pydantic_core import PydanticUndefined
    except Exception:
        PydanticUndefined = object()

    data: dict[str, Any] = {}
    for name, fld in model.model_fields.items():
        ann = getattr(fld, "annotation", None)
        default = getattr(fld, "default", None)
        if default is not None and default is not PydanticUndefined:
            data[name] = default
            continue

        origin = getattr(ann, "__origin__", None)
        args = getattr(ann, "__args__", ())

        if origin is list:
            data[name] = []
            continue
        if origin is dict:
            data[name] = {}
            continue

        from typing import Literal as Lit
        if origin is Lit and args:
            data[name] = args[0]
            continue

        if ann in (str,):
            data[name] = ""
        elif ann in (int,):
            data[name] = 0
        elif ann in (float,):
            data[name] = 0.0
        elif ann in (bool,):
            data[name] = False
        else:
            if hasattr(ann, "model_fields"):
                data[name] = dry_run_structured_output(ann)
            else:
                data[name] = None

    try:
        return model.model_validate(data).model_dump()
    except Exception:
        return data


# ---------------------------------------------------------------------------
# Workflow hashing
# ---------------------------------------------------------------------------


def workflow_hash(workflow: WorkflowDef) -> str:
    """Hash the workflow's source file content (strict resume drift check)."""
    source = getattr(workflow, "source_path", "") or ""
    if not source:
        return ""
    try:
        data = Path(source).read_bytes()
    except OSError:
        return ""
    return hashlib.sha256(data).hexdigest()
