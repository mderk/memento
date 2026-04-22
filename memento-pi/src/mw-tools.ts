import type { ExtensionAPI, ExtensionContext } from "@mariozechner/pi-coding-agent";
import { Type } from "@sinclair/typebox";
import type { MementoClient } from "./client.ts";
import type { ActionBase, AskUserAction, SubagentAction, WorkflowAction } from "./types.ts";

type Tool = ReturnType<ExtensionAPI["getAllTools"]>[number];

export interface RelayToolsContext {
	client: MementoClient;
	childRunId: string;
	ctx: ExtensionContext;
	/** Called when _mw_next encounters a subagent action it should delegate. */
	onNestedSubagent?: (
		action: SubagentAction,
	) => Promise<{ output: string; structured_output: unknown; error?: string }>;
	/** Captured terminal payload — set when child completes/halts/errors. Lets the driver know to stop. */
	terminal?: { type: "completed" | "halted" | "error" | "cancelled"; payload: unknown };
}

/**
 * Build the three relay tools (_mw_next, _mw_submit, _mw_status) bound to a
 * specific child run_id. Intended to be injected into a relay sub-session's
 * tool list alongside the allow-listed pi tools.
 *
 * _mw_next auto-resolves ask_user (via ctx.ui) and delegates nested subagent
 * actions to `onNestedSubagent` (if provided). The LLM only ever sees:
 *  - prompt actions (as prompt_text to answer)
 *  - terminal signals (completed/halted/error)
 *  - unsupported action types (returned as-is for LLM to reject)
 */
export function buildRelayTools(relayCtx: RelayToolsContext): Tool[] {
	const next: Tool = {
		name: "_mw_next",
		label: "workflow next",
		description:
			"Pull the next action from the workflow engine for the current child run. " +
			"Auto-resolves ask_user internally; returns only user-facing prompts or terminal status. " +
			"Call this first, then answer any prompt it returns, then call _mw_submit.",
		parameters: Type.Object({}),
		async execute(_id, _params, _signal, _onUpdate, _ctx) {
			try {
				let action = await nextFor(relayCtx.client, relayCtx.childRunId);
				while (true) {
					if (isTerminalAction(action)) {
						relayCtx.terminal = {
							type: action.action as "completed" | "halted" | "error" | "cancelled",
							payload: action,
						};
						return {
							content: [{ type: "text", text: describeTerminal(action) }],
							details: { terminal: true, action: action.action },
						};
					}
					if (action.action === "ask_user") {
						const ask = action as AskUserAction;
						const answer = await resolveAskUser(ask, relayCtx.ctx);
						action = (await relayCtx.client.call("submit", {
							run_id: ask.run_id,
							exec_key: ask.exec_key,
							output: answer ?? "",
							status: answer == null ? "failure" : "success",
						})) as WorkflowAction;
						continue;
					}
					if (action.action === "subagent" && relayCtx.onNestedSubagent) {
						const sub = action as SubagentAction;
						const result = await relayCtx.onNestedSubagent(sub);
						action = (await relayCtx.client.call("submit", {
							run_id: sub.run_id,
							exec_key: sub.exec_key,
							output: result.output,
							structured_output: result.structured_output,
							status: result.error ? "failure" : "success",
							error: result.error ?? null,
						})) as WorkflowAction;
						continue;
					}
					if (action.action === "prompt") {
						return {
							content: [{ type: "text", text: describePrompt(action) }],
							details: {
								exec_key: (action as { exec_key: string }).exec_key,
								run_id: action.run_id,
								hasSchema: Boolean((action as { json_schema?: unknown }).json_schema),
							},
						};
					}
					return {
						content: [
							{
								type: "text",
								text: `Unsupported action type '${action.action}' in relay child. Call _mw_submit with status=failure.`,
							},
						],
						isError: true,
						details: { action: action.action },
					};
				}
			} catch (err) {
				return {
					content: [{ type: "text", text: `_mw_next failed: ${(err as Error).message}` }],
					isError: true,
					details: {},
				};
			}
		},
	};

	const submit: Tool = {
		name: "_mw_submit",
		label: "workflow submit",
		description:
			"Submit the result of the current pending prompt for this child run. " +
			"Call after answering the prompt returned by _mw_next. " +
			"For schema-backed prompts put the JSON ONLY in structured_output; leave output empty.",
		parameters: Type.Object({
			exec_key: Type.String({ description: "exec_key from the last _mw_next result" }),
			output: Type.Optional(
				Type.String({ description: "Free-form text result (leave empty when using structured_output)" }),
			),
			structured_output: Type.Optional(
				Type.Any({ description: "Structured JSON result (when the prompt has a schema)" }),
			),
			status: Type.Optional(Type.Union([Type.Literal("success"), Type.Literal("failure")])),
			error: Type.Optional(Type.String()),
		}),
		async execute(_id, params, _signal, _onUpdate, _ctx) {
			try {
				const next = (await relayCtx.client.call("submit", {
					run_id: relayCtx.childRunId,
					exec_key: params.exec_key,
					output: params.output ?? "",
					structured_output: params.structured_output ?? null,
					status: params.status ?? "success",
					error: params.error ?? null,
				})) as WorkflowAction;
				if (isTerminalAction(next)) {
					relayCtx.terminal = {
						type: next.action as "completed" | "halted" | "error" | "cancelled",
						payload: next,
					};
				}
				return {
					content: [
						{ type: "text", text: `Submitted ${params.exec_key}; call _mw_next for the next action.` },
					],
					details: { nextActionType: next.action },
				};
			} catch (err) {
				return {
					content: [{ type: "text", text: `_mw_submit failed: ${(err as Error).message}` }],
					isError: true,
					details: {},
				};
			}
		},
	};

	const status: Tool = {
		name: "_mw_status",
		label: "workflow status",
		description: "Inspect the current state of this child workflow run (debugging only).",
		parameters: Type.Object({}),
		async execute(_id, _params, _signal, _onUpdate, _ctx) {
			try {
				const res = await relayCtx.client.call("status", { run_id: relayCtx.childRunId });
				return {
					content: [{ type: "text", text: JSON.stringify(res, null, 2) }],
					details: {},
				};
			} catch (err) {
				return {
					content: [{ type: "text", text: `_mw_status failed: ${(err as Error).message}` }],
					isError: true,
					details: {},
				};
			}
		},
	};

	return [next, submit, status];
}

async function nextFor(client: MementoClient, runId: string): Promise<WorkflowAction> {
	return (await client.call("next", { run_id: runId })) as WorkflowAction;
}

function isTerminalAction(a: ActionBase): boolean {
	return a.action === "completed" || a.action === "halted" || a.action === "error" || a.action === "cancelled";
}

function describeTerminal(a: WorkflowAction): string {
	if (a.action === "completed") {
		const summary = (a as { summary?: unknown }).summary;
		return `Workflow completed. summary=${summary ? JSON.stringify(summary) : "{}"}`;
	}
	if (a.action === "halted") return `Workflow halted: ${(a as { reason?: string }).reason ?? ""}`;
	if (a.action === "error") return `Workflow error: ${(a as { message?: string }).message ?? ""}`;
	return "Workflow cancelled.";
}

function describePrompt(a: WorkflowAction): string {
	const prompt = (a as { prompt?: string }).prompt ?? "";
	const execKey = (a as { exec_key?: string }).exec_key ?? "";
	const schema = (a as { json_schema?: unknown }).json_schema;
	const parts: string[] = [];
	parts.push(`=== PROMPT [exec_key=${execKey}] ===`);
	parts.push(prompt);
	if (schema) {
		parts.push("");
		parts.push(
			"This prompt expects a structured JSON result matching its output_schema. " +
				"When you call _mw_submit, put the JSON ONLY in structured_output; leave output empty.",
		);
	}
	parts.push("");
	parts.push(`Answer the prompt above, then call _mw_submit with exec_key=${execKey}.`);
	return parts.join("\n");
}

async function resolveAskUser(action: AskUserAction, ctx: ExtensionContext): Promise<string | null> {
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
	const answer = await ctx.ui.input("workflow", message, action.default ?? "");
	return answer ?? null;
}
