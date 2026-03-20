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

from .engine.types import (
    StepResult,
    StructuredOutput,
    WorkflowContext,
    WorkflowDef,
)

import logging

logger = logging.getLogger("workflow-engine")

_VAR_RE = re.compile(r"\{\{([\w.\-]+)\}\}")


# ---------------------------------------------------------------------------
# Template substitution
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


# Threshold in characters for externalizing large values to files.
_EXTERN_THRESHOLD = 1000


def substitute_with_files(
    template: str,
    ctx: WorkflowContext,
    artifacts_dir: Path,
) -> tuple[str, list[str]]:
    """Like substitute, but writes large values to context files.

    Returns (prompt_text, context_file_paths).  Values smaller than
    _EXTERN_THRESHOLD are inlined as before.
    """
    context_files: list[str] = []

    def _externalize(varname: str, content: str, ext: str) -> str:
        file_path = artifacts_dir / f"context_{varname}.{ext}"
        if not file_path.resolve().is_relative_to(artifacts_dir.resolve()):
            raise ValueError(f"context file escapes artifacts_dir: {file_path}")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        context_files.append(str(file_path))
        return f"(data externalized to context_{varname}.{ext} — read from context_files)"

    def _replace(m: re.Match) -> str:
        val = ctx.get_var(m.group(1))
        if val is None:
            return m.group(0)
        if isinstance(val, (dict, list)):
            serialized = json.dumps(val, indent=2)
            if len(serialized) > _EXTERN_THRESHOLD:
                return _externalize(m.group(1).replace(".", "_"), serialized, "json")
            return serialized
        if isinstance(val, str) and len(val) > _EXTERN_THRESHOLD:
            return _externalize(m.group(1).replace(".", "_"), val, "txt")
        return str(val)

    result = _VAR_RE.sub(_replace, template)
    return result, context_files


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
        logger.warning(
            "Condition evaluation raised exception, treating as False", exc_info=True
        )
        return False


# ---------------------------------------------------------------------------
# Result identity helpers
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
    structured_output: StructuredOutput,
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
    except ImportError:
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


def merge_child_results(
    parent_results_scoped: dict,
    parent_results: dict,
    child_results_scoped: dict,
) -> None:
    """Merge child-produced results into parent (collision-safe).

    Skips keys already present in parent (inherited results).
    Used by both runner.py (run_id lookup) and state.py (direct RunState).
    """
    for key, r in child_results_scoped.items():
        if key in parent_results_scoped:
            continue  # inherited from parent
        parent_results_scoped[key] = r
        if r.results_key:
            parent_results[r.results_key] = r


def compute_totals(results_scoped: dict) -> dict[str, Any]:
    """Compute duration/cost/step_count totals from results_scoped.

    Returns a dict suitable for CompletedAction.totals or write_meta kwargs.
    Shared by actions._build_completed_action and runner._write_terminal_meta.
    """
    total_cost = 0.0
    total_duration = 0.0
    steps_by_type: dict[str, int] = {}
    has_cost = False
    for r in results_scoped.values():
        if r.status in ("skipped", "dry_run"):
            continue
        total_duration += r.duration
        if r.cost_usd is not None:
            total_cost += r.cost_usd
            has_cost = True
        if r.step_type:
            steps_by_type[r.step_type] = steps_by_type.get(r.step_type, 0) + 1

    totals: dict[str, Any] = {
        "duration": round(total_duration, 3),
        "step_count": len(
            [
                r
                for r in results_scoped.values()
                if r.status not in ("skipped", "dry_run")
            ]
        ),
    }
    if has_cost:
        totals["cost_usd"] = round(total_cost, 6)
    if steps_by_type:
        totals["steps_by_type"] = steps_by_type
    return totals


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
