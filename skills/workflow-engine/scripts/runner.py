#!/usr/bin/env python3
"""CLI entry point for the imperative workflow engine.

Usage:
    python runner.py <workflow-name> [--var key=value ...] [--cwd path] [--dry-run]
                     [--workflow-dir path] [--answer step=value ...]
    python runner.py resume [--cwd path] [--answer step=value ...]

In non-TTY mode (Claude Code), the engine pauses at prompts by printing a
JSON question to stdout and saving state to .workflow-state/<run_id>/.
Use the `resume` subcommand with --answer to continue.

Examples:
    python runner.py development --var task="Add login" --cwd /my/project
    python runner.py code-review --dry-run
    python runner.py resume --cwd /my/project --answer confirm=yes
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
import uuid
from pathlib import Path

from .engine import PresetIOHandler, StopForInput, StopIOHandler, workflow_hash
from .types import StepResult, WorkflowContext


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run imperative workflows with deterministic step execution.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("workflow", help="Workflow name or 'resume' to continue a paused workflow")
    parser.add_argument("--var", action="append", default=[], metavar="KEY=VALUE",
                        help="Set a workflow variable (repeatable)")
    parser.add_argument("--cwd", default=".", help="Working directory (default: current)")
    parser.add_argument("--dry-run", action="store_true", help="Show steps without executing")
    parser.add_argument("--workflow-dir", action="append", default=[], metavar="PATH",
                        help="Additional workflow search directory (repeatable)")
    parser.add_argument("--answer", action="append", default=[], metavar="STEP=VALUE",
                        help="Pre-supply answer for a PromptStep (repeatable)")
    parser.add_argument("--run-id", default=None, metavar="ID",
                        help="Resume a specific run (default: most recent paused run)")
    parser.add_argument("--output", default=None, metavar="PATH",
                        help="Write output to file (use '; cat PATH' to deliver reliably)")
    return parser


def _parse_kv(args: list[str], label: str) -> dict[str, str]:
    """Parse KEY=VALUE arguments into a dict.

    Uses rpartition to split on the LAST '=' so that keys containing '='
    (e.g. 'par:block[i=0]/step/ask:hash') are parsed correctly.
    """
    result: dict[str, str] = {}
    for item in args:
        if "=" not in item:
            print(f"Error: --{label} must be KEY=VALUE, got: {item}", file=sys.stderr)
            sys.exit(1)
        key, _, value = item.rpartition("=")
        result[key.strip()] = value.strip()
    return result


def _find_checkpoint(cwd: Path, run_id: str | None = None) -> Path | None:
    """Find a checkpoint in .workflow-state/.

    If run_id is given, look up that specific run. Otherwise fall back
    to the most recently modified checkpoint.
    """
    ws_root = cwd / ".workflow-state"
    if not ws_root.is_dir():
        return None
    if run_id:
        exact = ws_root / run_id / "checkpoint.json"
        return exact if exact.is_file() else None
    candidates = list(ws_root.glob("*/checkpoint.json"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _cleanup_state(checkpoint_file: Path, cwd: Path) -> None:
    """Remove checkpoint file; keep log files and their directories."""
    if checkpoint_file.exists():
        checkpoint_file.unlink()
    state_dir = checkpoint_file.parent
    # Keep dir if log or other files remain
    if state_dir.exists() and not any(state_dir.iterdir()):
        state_dir.rmdir()
    ws_root = cwd / ".workflow-state"
    if ws_root.exists() and not any(ws_root.iterdir()):
        ws_root.rmdir()


def _rebuild_results_view(ctx: WorkflowContext) -> None:
    """Rebuild ctx.results (convenience view) from ctx.results_scoped."""
    ctx.results = {}
    # Deterministic: apply in increasing order
    for r in sorted(ctx.results_scoped.values(), key=lambda x: (x.order, x.exec_key)):
        if r.results_key:
            ctx.results[r.results_key] = r


async def _run(args: argparse.Namespace) -> int:
    from .engine import execute_workflow
    from .loader import discover_workflows

    # Redirect stdout to file when --output is specified.
    # Bash tool may lose stdout from long-running SDK processes;
    # writing to a file + '; cat file' afterwards is reliable.
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sys.stdout = open(output_path, "w", encoding="utf-8")  # noqa: SIM115

    cwd_resolved = Path(args.cwd).resolve()
    answers = _parse_kv(args.answer, "answer")

    # --- Resume mode: load everything from checkpoint ---
    if args.workflow == "resume":
        checkpoint_file = _find_checkpoint(cwd_resolved, args.run_id)
        if not checkpoint_file:
            print("Error: no pending workflow found in .workflow-state/", file=sys.stderr)
            return 1
        prior = json.loads(checkpoint_file.read_text(encoding="utf-8"))
        run_id = prior["run_id"]
        workflow_name = prior["workflow"]
        workflow_dirs = prior["workflow_dirs"]
        variables = prior.get("variables", {})
        variables["run_id"] = run_id
        # Build registry from saved paths
        search_paths = [cwd_resolved / ".workflows"]
        for d in workflow_dirs:
            search_paths.append(Path(d))
        registry = discover_workflows(*search_paths)
        if workflow_name not in registry:
            print(f"Error: workflow '{workflow_name}' not found in saved paths", file=sys.stderr)
            return 1
        workflow = registry[workflow_name]
        # Strict drift check: refuse resume if workflow source changed.
        prior_hash = prior.get("workflow_hash", "")
        current_hash = workflow_hash(workflow)
        if prior_hash and current_hash and prior_hash != current_hash:
            print(
                "Error: workflow definition changed since checkpoint was created; refusing to resume.\n"
                f"  checkpoint_hash: {prior_hash}\n"
                f"  current_hash:    {current_hash}\n"
                f"  source:          {workflow.source_path}",
                file=sys.stderr,
            )
            return 1
    else:
        # --- Fresh run ---
        run_id = uuid.uuid4().hex[:12]
        variables = _parse_kv(args.var, "var")
        variables["run_id"] = run_id
        variables.setdefault(
            "engine_scripts_dir",
            str(Path(__file__).resolve().parent),
        )
        search_paths = [cwd_resolved / ".workflows"]
        workflow_dirs = []
        for extra in args.workflow_dir:
            resolved = str(Path(extra).resolve())
            search_paths.append(Path(resolved))
            workflow_dirs.append(resolved)
        registry = discover_workflows(*search_paths)
        if args.workflow not in registry:
            print(f"Error: Unknown workflow '{args.workflow}'", file=sys.stderr)
            print(f"Available: {', '.join(sorted(registry))}", file=sys.stderr)
            return 1
        workflow = registry[args.workflow]
        current_hash = workflow_hash(workflow)

    # Create IOHandler: auto-detect TTY vs subprocess
    if sys.stdin.isatty():
        io_handler = PresetIOHandler(answers) if answers else None
    else:
        io_handler = StopIOHandler(answers)

    ctx = WorkflowContext(
        variables=variables,
        cwd=str(cwd_resolved),
        dry_run=args.dry_run,
        io_handler=io_handler,
    )

    # Inject prior results on resume
    if args.workflow == "resume":
        injected = {
            k: StepResult(**data)
            for k, data in prior.get("results_scoped", {}).items()
        }
        ctx.injected_results_scoped = dict(injected)
        ctx.results_scoped = dict(injected)
        # Restore order counter so new results continue ordering deterministically.
        if injected:
            ctx._order_seq = max(r.order for r in injected.values())  # type: ignore[attr-defined]
        _rebuild_results_view(ctx)

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Running workflow: {workflow.name}")
    print(f"  Description: {workflow.description}")
    print(f"  Blocks: {len(workflow.blocks)}")
    if variables:
        print(f"  Variables: {variables}")
    print()

    # State directory + logging
    state_dir = cwd_resolved / ".workflow-state" / run_id
    checkpoint_file = state_dir / "checkpoint.json"
    state_dir.mkdir(parents=True, exist_ok=True)

    log_file = state_dir / "execution.log"
    wf_logger = logging.getLogger("workflow-engine")
    wf_logger.setLevel(logging.DEBUG)
    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-5s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    wf_logger.addHandler(file_handler)
    print(f"Log: {log_file}")

    t0 = time.time()
    try:
        results = await execute_workflow(workflow, ctx, registry=registry)
    except StopForInput as stop:
        wf_logger.removeHandler(file_handler)
        file_handler.close()
        # Save full state so `resume` can reconstruct everything
        checkpoint = {
            "run_id": run_id,
            "workflow": workflow.name,
            "workflow_dirs": workflow_dirs if args.workflow != "resume" else prior["workflow_dirs"],
            "workflow_hash": current_hash if args.workflow != "resume" else prior.get("workflow_hash", current_hash),
            "results_scoped": {k: v.model_dump() for k, v in ctx.results_scoped.items()},
            "variables": ctx.variables,
        }
        checkpoint_file.write_text(json.dumps(checkpoint), encoding="utf-8")

        # Build structured question block for the invoking agent.
        engine_path = str(Path(__file__).resolve().parent.parent / "run.py")
        question_file = checkpoint_file.parent / "question.json"
        output_flag = f" --output {state_dir / 'output.txt'}"
        resume_cmd = (
            f"python {engine_path} resume --cwd {cwd_resolved} --run-id {run_id}"
            f"{output_flag} "
            f"--answer {stop.key}=<ANSWER>"
            f"; cat {state_dir / 'output.txt'}"
        )
        question_block = {
            "type": "workflow_question",
            "key": stop.key,
            "step_name": stop.step_name,
            "prompt_type": stop.prompt_type,
            "message": stop.message,
            "options": stop.options,
            "default": stop.default,
            "strict": stop.strict,
            "resume_command": resume_cmd,
        }

        # Build the full output text.
        output_lines = [json.dumps(question_block, indent=2), ""]
        instruction_parts = [
            "INSTRUCTION: Present the question above to the user and collect their answer.",
        ]
        if stop.options and stop.strict:
            instruction_parts.append(
                f"Valid answers (exact values only): {stop.options}. "
                "If the user picks 'Other' or gives free-text instead of a listed option, "
                "do NOT call resume. Instead, explain that the workflow requires an exact "
                "option and re-ask with two choices: "
                "['Re-ask the question', 'Stop the workflow']. "
                "If they choose 'Re-ask the question', present the original question again. "
                "If they choose 'Stop the workflow' or pick 'Other', "
                f"cancel the workflow: remove .workflow-state/{run_id}/ "
                "and inform the user that the workflow was cancelled."
            )
        instruction_parts.append(
            "After the user answers, run resume_command replacing <ANSWER> with the value."
        )
        output_lines.append("\n".join(instruction_parts))
        full_output = "\n".join(output_lines)

        # Write question to file as backup.
        question_file.write_text(full_output, encoding="utf-8")
        print(full_output)
        return 0

    elapsed = time.time() - t0
    _cleanup_state(checkpoint_file, cwd_resolved)

    # Print results summary
    print("\n" + "=" * 60)
    print("Results Summary")
    print("=" * 60)

    total_cost = 0.0
    for r in results:
        icon = {"success": "+", "failure": "!", "skipped": "-", "dry_run": "~"}.get(r.status, "?")
        cost_str = f" (${r.cost_usd:.4f})" if r.cost_usd else ""
        dur_str = f" [{r.duration:.1f}s]" if r.duration > 0 else ""
        label = r.results_key or r.name
        if r.exec_key and r.exec_key != label:
            label = f"{label}  ({r.exec_key})"
        print(f"  [{icon}] {label}: {r.status}{dur_str}{cost_str}")
        if r.error:
            print(f"      Error: {r.error}")
        if r.cost_usd:
            total_cost += r.cost_usd

    print(f"\nTotal time: {elapsed:.1f}s")
    if total_cost > 0:
        print(f"Total cost: ${total_cost:.4f}")

    failures = [r for r in results if r.status == "failure"]
    wf_logger.removeHandler(file_handler)
    file_handler.close()
    print(f"\nLog saved: {log_file}")
    if failures:
        print(f"\n{len(failures)} step(s) failed.")
        return 1

    print("\nWorkflow completed successfully.")
    return 0


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    exit_code = asyncio.run(_run(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
