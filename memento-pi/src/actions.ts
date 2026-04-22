import type { ExtensionAPI, ExtensionContext } from "@mariozechner/pi-coding-agent";
import type { MementoClient } from "./client.ts";
import { runLLMStep } from "./llm-step.ts";
import { runRelaySession } from "./relay-session.ts";
import { getActive, setActive } from "./state.ts";
import {
	type ActionBase,
	isTerminal,
	type ParallelAction,
	type PromptAction,
	type SubagentAction,
	type WorkflowAction,
} from "./types.ts";
import { updateWidget } from "./widget.ts";

export interface ProcessOptions {
	workflowName: string;
	client: MementoClient;
	ctx: ExtensionContext;
	pi: ExtensionAPI;
}

/**
 * Process actions returned by the engine. Handles ask_user, leaf subagent, relay
 * subagent, and parallel actions inline. Stops when the chain reaches a `prompt`
 * (inline LLM step that needs the main session), a terminal state, or an
 * unsupported action type. Keeps activeRun in sync.
 */
export async function processActions(first: ActionBase, opts: ProcessOptions): Promise<void> {
	let action = first as WorkflowAction;

	while (true) {
		const warnings = (action as ActionBase).warnings;
		if (warnings?.length) {
			for (const w of warnings) opts.ctx.ui.notify(`workflow: ${w}`, "warning");
		}

		if (isTerminal(action)) {
			await handleTerminal(action, opts);
			return;
		}

		if (action.action === "ask_user") {
			const answer = await askUser(action, opts.ctx);
			if (answer == null) {
				opts.ctx.ui.notify("ask_user cancelled — workflow paused", "warning");
				return;
			}
			const next = await opts.client.call("submit", {
				run_id: action.run_id,
				exec_key: action.exec_key,
				output: answer,
				status: "success",
			});
			action = next as WorkflowAction;
			continue;
		}

		if (action.action === "prompt") {
			setActive({
				runId: action.run_id,
				workflowName: opts.workflowName,
				pending: action as PromptAction,
				stepCount: (getActive()?.stepCount ?? 0) + 1,
			});
			updateWidget(opts.ctx);
			opts.ctx.ui.notify(
				`workflow '${opts.workflowName}' awaiting inline step '${action.exec_key}' — send any message to continue`,
				"info",
			);
			return;
		}

		if (action.action === "subagent") {
			const sub = action as SubagentAction;
			setActive({
				runId: sub.run_id,
				workflowName: opts.workflowName,
				pending: sub,
				stepCount: (getActive()?.stepCount ?? 0) + 1,
			});
			updateWidget(opts.ctx);

			const result = sub.relay && sub.child_run_id
				? await runRelaySession(sub, opts.pi, opts.ctx, opts.client)
				: await runLLMStep(sub, opts.pi, opts.ctx);

			const next = await opts.client.call("submit", {
				run_id: sub.run_id,
				exec_key: sub.exec_key,
				output: result.output,
				structured_output: result.structured_output,
				status: result.error ? "failure" : "success",
				error: result.error ?? null,
			});
			action = next as WorkflowAction;
			continue;
		}

		if (action.action === "parallel") {
			const result = await runParallel(action as ParallelAction, opts);
			const next = await opts.client.call("submit", {
				run_id: action.run_id,
				exec_key: action.exec_key,
				output: "",
				structured_output: result.lanes,
				status: result.anyFailure ? "failure" : "success",
				error: result.anyFailure ? "one or more parallel lanes failed" : null,
			});
			action = next as WorkflowAction;
			continue;
		}

		opts.ctx.ui.notify(`unknown action type: ${(action as ActionBase).action}`, "error");
		return;
	}
}

interface ParallelRunResult {
	lanes: Array<{ child_run_id: string; exec_key: string; output: string; structured_output: unknown; error?: string }>;
	anyFailure: boolean;
}

/**
 * Drive all lanes sequentially reusing the relay machinery. Each lane is a
 * SubagentAction(relay=true) synthesised from the ParallelAction lane entry.
 * Concurrent execution is a v2 optimisation.
 */
async function runParallel(action: ParallelAction, opts: ProcessOptions): Promise<ParallelRunResult> {
	const results: ParallelRunResult["lanes"] = [];
	let anyFailure = false;
	for (const lane of action.lanes) {
		const laneAction: SubagentAction = {
			action: "subagent",
			run_id: action.run_id,
			exec_key: lane.exec_key,
			prompt: lane.prompt,
			relay: lane.relay ?? true,
			child_run_id: lane.child_run_id,
			model: action.model ?? undefined,
		};
		const r = await runRelaySession(laneAction, opts.pi, opts.ctx, opts.client);
		if (r.error) anyFailure = true;
		results.push({
			child_run_id: lane.child_run_id,
			exec_key: lane.exec_key,
			output: r.output,
			structured_output: r.structured_output,
			error: r.error,
		});
	}
	return { lanes: results, anyFailure };
}

async function askUser(
	action: { prompt_type: string; message: string; options?: string[] | null; default?: string | null },
	ctx: ExtensionContext,
): Promise<string | null> {
	const message = action.message;
	if (action.prompt_type === "confirm") {
		const ok = await ctx.ui.confirm("workflow", message);
		return ok ? "yes" : "no";
	}
	if (action.prompt_type === "choice") {
		const opts = action.options ?? [];
		const picked = await ctx.ui.select(message, opts);
		return picked ?? null;
	}
	if (action.prompt_type === "input") {
		const answer = await ctx.ui.input("workflow", message, action.default ?? "");
		return answer ?? null;
	}
	const fallback = await ctx.ui.input("workflow", message, action.default ?? "");
	return fallback ?? null;
}

async function handleTerminal(
	action: WorkflowAction & { action: "completed" | "halted" | "error" | "cancelled" },
	opts: ProcessOptions,
): Promise<void> {
	setActive(null);
	updateWidget(opts.ctx);
	if (action.action === "completed") {
		opts.ctx.ui.notify(`workflow '${opts.workflowName}' completed`, "success");
	} else if (action.action === "halted") {
		opts.ctx.ui.notify(`workflow halted: ${action.reason}`, "warning");
	} else if (action.action === "error") {
		opts.ctx.ui.notify(`workflow error: ${action.message}`, "error");
	} else {
		opts.ctx.ui.notify(`workflow cancelled`, "info");
	}
}
