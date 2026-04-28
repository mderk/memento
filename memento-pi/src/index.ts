import { readFileSync } from "node:fs";
import type { ExtensionAPI, ExtensionContext } from "@mariozechner/pi-coding-agent";
import { Type } from "@sinclair/typebox";
import { createAgentSession, SessionManager } from "@mariozechner/pi-coding-agent";
import { processActions } from "./actions.ts";
import {
	ensurePlanExists,
	findProtocolCandidates,
	prepareCreateProtocol,
	readLastRun,
	toWorkflowPath,
} from "./commands/protocols.ts";
import { renderPendingPrompt } from "./render.ts";
import { getConfig } from "./config.ts";
import { runAgentPrompt } from "./llm-step.ts";
import { defaultRuntimeDeps, type ClientLike, type RuntimeDeps } from "./runtime.ts";
import { abortActiveAutoRun, getActive, setActive } from "./state.ts";
import { updateWidget } from "./widget.ts";

/**
 * Normalize submit params to avoid duplicating data into the session/checkpoint:
 *  - If output_file is given, read it and treat as the result.
 *  - If both output (string) and structured_output (object) are present, and
 *    output is just JSON-stringified structured_output, drop output.
 *  - If structured_output is present but output is missing, leave output empty.
 */
function normalizeSubmit(params: {
	output?: string;
	structured_output?: unknown;
	output_file?: string;
}): { output: string; structured_output: unknown } {
	let output = params.output ?? "";
	let structured = params.structured_output ?? null;

	if (params.output_file) {
		try {
			const raw = readFileSync(params.output_file, "utf-8");
			try {
				structured = JSON.parse(raw);
				output = "";
			} catch {
				output = raw;
			}
		} catch (err) {
			throw new Error(`failed to read output_file ${params.output_file}: ${(err as Error).message}`);
		}
	}

	if (output && structured && typeof structured === "object") {
		try {
			if (output.trim() === JSON.stringify(structured)) output = "";
		} catch {
			/* ignore */
		}
	}

	return { output, structured_output: structured };
}

async function startWorkflow(
	name: string,
	client: ClientLike,
	ctx: ExtensionContext,
	pi: ExtensionAPI,
	deps: RuntimeDeps,
	options: { variables?: Record<string, unknown>; resume?: string } = {},
): Promise<boolean> {
	if (getActive()) {
		ctx.ui.notify(`workflow '${getActive()?.workflowName}' is already active — finish or /wf cancel first`, "error");
		return false;
	}
	const action = await client.call("start", {
		workflow: name,
		cwd: process.cwd(),
		variables: options.variables ?? {},
		resume: options.resume ?? "",
	});
	if (action.action === "error") {
		ctx.ui.notify(`start failed: ${action.message}`, "error");
		return false;
	}
	await processActions(action, { workflowName: name, client, ctx, pi, deps });
	const run = getActive();
	if (run) {
		ctx.ui.notify(`started '${name}' (run ${run.runId.slice(0, 12)})`, "info");
		if (run.mode === "handoff") {
			pi.sendUserMessage("Continue the active workflow.", { deliverAs: "followUp" });
		}
	}
	return true;
}

async function chooseProtocolDir(arg: string, ctx: ExtensionContext): Promise<string> {
	const candidates = findProtocolCandidates(arg, process.cwd());
	if (candidates.length === 0) throw new Error(`no protocol matched: ${arg || "<empty>"}`);
	if (candidates.length === 1) return candidates[0]!.protocolDir;
	const labels = candidates.map((candidate) => candidate.label);
	const picked = await ctx.ui.select("Matching protocols", labels);
	const match = candidates.find((candidate) => candidate.label === picked);
	if (!match) throw new Error("protocol selection cancelled");
	return match.protocolDir;
}

function backendToolResult(result: unknown) {
	return {
		content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }],
		details: result as Record<string, unknown>,
	};
}

function registerClaudeCompatTools(pi: ExtensionAPI, getClient: () => ClientLike): void {
	const prefix = "mcp__plugin_memento-workflow_memento-workflow__";

	const register = (
		name: string,
		description: string,
		parameters: ReturnType<typeof Type.Object>,
		method: string,
		mapParams?: (params: Record<string, unknown>) => Record<string, unknown>,
	) => {
		pi.registerTool({
			name: `${prefix}${name}`,
			label: `memento-workflow ${name}`,
			description,
			parameters,
			async execute(_toolCallId, params) {
				try {
					const result = await getClient().call(method, mapParams ? mapParams(params) : params);
					return backendToolResult(result);
				} catch (err) {
					return {
						content: [{ type: "text", text: `${name} failed: ${(err as Error).message}` }],
						isError: true,
						details: {},
					};
				}
			},
		});
	};

	register(
		"start",
		"Claude-compat shim for memento-workflow start().",
		Type.Object({
			workflow: Type.String(),
			variables: Type.Optional(Type.Any()),
			cwd: Type.Optional(Type.String()),
			workflow_dirs: Type.Optional(Type.Array(Type.String())),
			resume: Type.Optional(Type.String()),
			dry_run: Type.Optional(Type.Boolean()),
			shell_log: Type.Optional(Type.Boolean()),
		}),
		"start",
	);

	register(
		"resume",
		"Claude-compat shim for memento-workflow resume().",
		Type.Object({
			run_id: Type.String(),
			cwd: Type.Optional(Type.String()),
			workflow_dirs: Type.Optional(Type.Array(Type.String())),
			shell_log: Type.Optional(Type.Boolean()),
		}),
		"resume",
	);

	register(
		"submit",
		"Claude-compat shim for memento-workflow submit().",
		Type.Object({
			run_id: Type.String(),
			exec_key: Type.String(),
			output: Type.Optional(Type.String()),
			structured_output: Type.Optional(Type.Any()),
			status: Type.Optional(Type.Union([Type.Literal("success"), Type.Literal("failure")])),
			error: Type.Optional(Type.String()),
			duration: Type.Optional(Type.Number()),
			cost_usd: Type.Optional(Type.Number()),
			model: Type.Optional(Type.String()),
			shell_log: Type.Optional(Type.Boolean()),
		}),
		"submit",
	);

	register(
		"next",
		"Claude-compat shim for memento-workflow next().",
		Type.Object({
			run_id: Type.String(),
			shell_log: Type.Optional(Type.Boolean()),
		}),
		"next",
	);

	register(
		"cancel",
		"Claude-compat shim for memento-workflow cancel().",
		Type.Object({
			run_id: Type.String(),
		}),
		"cancel",
	);

	register(
		"list_workflows",
		"Claude-compat shim for memento-workflow list_workflows().",
		Type.Object({
			cwd: Type.Optional(Type.String()),
			workflow_dirs: Type.Optional(Type.Array(Type.String())),
		}),
		"list_workflows",
	);

	register(
		"status",
		"Claude-compat shim for memento-workflow status().",
		Type.Object({
			run_id: Type.String(),
		}),
		"status",
	);
}

export function createMementoExtension(overrides: Partial<RuntimeDeps> = {}) {
	const deps: RuntimeDeps = { ...defaultRuntimeDeps, ...overrides };
	return function mementoExtension(pi: ExtensionAPI) {
		const config = deps.resolveServerConfig();
		let client: ClientLike | null = null;

		const getClient = (): ClientLike => {
			if (!client) client = deps.createClient(config);
			return client;
		};

		pi.on("session_start", async (_event, ctx) => {
		try {
			getClient();
		} catch (err) {
			ctx.ui.notify(`memento-pi failed to start: ${(err as Error).message}`, "error");
		}
	});

		pi.on("session_shutdown", async () => {
		abortActiveAutoRun("session shutdown");
		setActive(null);
		if (client) {
			await client.shutdown();
			client = null;
		}
	});

		pi.on("before_agent_start", async (event) => {
		const run = getActive();
		process.stderr.write(`[mw] before_agent_start: hasActive=${run ? "yes" : "no"} pending=${run?.pending.exec_key ?? "none"}\n`);
		if (!run || run.mode !== "handoff") return;
		if (run.pending.action !== "prompt" && !(run.pending.action === "subagent" && !run.pending.relay)) return;
		const block = renderPendingPrompt(run, run.pending);
		return { systemPrompt: `${event.systemPrompt}\n\n${block}` };
	});

		registerClaudeCompatTools(pi, getClient);

		pi.registerTool({
			name: "AskUserQuestion",
			label: "Ask user question",
			description: "Ask the user a question and return the selected or typed answer.",
			parameters: Type.Object({
				question: Type.String(),
				options: Type.Optional(Type.Array(Type.Object({ label: Type.String(), value: Type.Optional(Type.String()) }))),
				multiSelect: Type.Optional(Type.Boolean()),
				placeholder: Type.Optional(Type.String()),
			}),
			async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
				const options = (params.options ?? []) as Array<{ label: string; value?: string }>;
				if (options.length > 0) {
					const labels = options.map((option) => option.label);
					const picked = await ctx.ui.select(params.question, labels);
					if (picked == null) return { content: [{ type: "text", text: "" }], details: { answer: "" } };
					const match = options.find((option) => option.label === picked);
					const answer = match?.value ?? picked;
					return { content: [{ type: "text", text: answer }], details: { answer } };
				}
				const answer = await ctx.ui.input("question", params.placeholder ?? params.question);
				return { content: [{ type: "text", text: answer ?? "" }], details: { answer: answer ?? "" } };
			},
		});

		pi.registerTool({
			name: "Agent",
			label: "Agent",
			description: "Run an isolated agent session with the given prompt and return its final response.",
			parameters: Type.Object({
				prompt: Type.String(),
				model: Type.Optional(Type.String()),
			}),
			async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
				const result = await runAgentPrompt(params.prompt, pi, ctx, {
					model: params.model ?? null,
					parseJson: false,
				});
				if (result.error) {
					return {
						content: [{ type: "text", text: result.error }],
						isError: true,
						details: {},
					};
				}
				return { content: [{ type: "text", text: result.output }], details: { output: result.output } };
			},
		});

		pi.registerTool({
		name: "workflow_submit",
		label: "Submit workflow step",
		description:
			"Submit the result of the currently pending workflow LLM step. Call exactly once per pending exec_key. " +
			"The active run_id and exec_key are shown in the <workflow-pending> block of the system prompt. " +
			"The result will contain the NEXT step's prompt if there is one — read it and call workflow_submit again to continue the chain.",
		parameters: Type.Object({
			run_id: Type.String({ description: "run_id from <workflow-pending>" }),
			exec_key: Type.String({ description: "exec_key from <workflow-pending>" }),
			output: Type.Optional(
				Type.String({
					description:
						"Free-form text output. For steps with a schema, leave empty or use a one-line summary only — do NOT duplicate the JSON here.",
				}),
			),
			structured_output: Type.Optional(
				Type.Any({
					description:
						"Structured JSON output (must match output_schema when the step has one). Omit when there is no schema.",
				}),
			),
			output_file: Type.Optional(
				Type.String({
					description:
						"Path to a file containing the result (preferred for large outputs). If the file is valid JSON, it becomes structured_output; otherwise it becomes output. Leave output and structured_output unset when using this.",
				}),
			),
			status: Type.Optional(
				Type.Union([Type.Literal("success"), Type.Literal("failure")], {
					description: "success (default) or failure",
				}),
			),
			error: Type.Optional(Type.String({ description: "Error message if status=failure" })),
		}),
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const run = getActive();
			process.stderr.write(`[mw] submit.execute: hasActive=${run ? "yes" : "no"} run=${run?.runId ?? "null"} pending=${run?.pending.exec_key ?? "null"}\n`);
			const isHandoffLLMStep = run?.mode === "handoff"
				&& (run.pending.action === "prompt" || (run.pending.action === "subagent" && !run.pending.relay));
			if (!run || !isHandoffLLMStep) {
				return {
					content: [{ type: "text", text: "No active workflow LLM step is waiting for submission." }],
					isError: true,
					details: {},
				};
			}
			if (params.run_id !== run.runId || params.exec_key !== run.pending.exec_key) {
				return {
					content: [
						{
							type: "text",
							text: `exec_key/run_id mismatch. Expected run_id=${run.runId} exec_key=${run.pending.exec_key}, got run_id=${params.run_id} exec_key=${params.exec_key}.`,
						},
					],
					isError: true,
					details: {},
				};
			}

			let normalized: { output: string; structured_output: unknown };
			try {
				normalized = normalizeSubmit({
					output: params.output,
					structured_output: params.structured_output,
					output_file: params.output_file,
				});
			} catch (err) {
				return {
					content: [{ type: "text", text: (err as Error).message }],
					isError: true,
					details: {},
				};
			}

			try {
				const next = await getClient().call("submit", {
					run_id: params.run_id,
					exec_key: params.exec_key,
					output: normalized.output,
					structured_output: normalized.structured_output,
					status: params.status ?? "success",
					error: params.error ?? null,
				});
				process.stderr.write(`[mw] engine submit returned: action=${next?.action} exec_key=${(next as any)?.exec_key ?? "none"}\n`);
				await processActions(next, {
					workflowName: run.workflowName,
					client: getClient(),
					ctx,
					pi,
					deps,
				});
				const after = getActive();
				let resultText: string;
				if (after?.mode === "handoff" && (after.pending.action === "prompt" || (after.pending.action === "subagent" && !after.pending.relay))) {
					const rendered = renderPendingPrompt(after, after.pending);
					resultText = `Step ${params.exec_key} submitted.\n\n${rendered}`;
				} else if (after) {
					resultText = `Step ${params.exec_key} submitted; workflow advanced to ${after.mode} (${after.pending.exec_key}).`;
				} else {
					resultText = `Step ${params.exec_key} submitted; workflow finished.`;
				}
				process.stderr.write(`[mw] submit result: hasAfter=${after ? "yes" : "no"} textLen=${resultText.length}\n`);
				return { content: [{ type: "text", text: resultText }], details: { nextActionType: next?.action } };
			} catch (err) {
				return {
					content: [{ type: "text", text: `submit failed: ${(err as Error).message}` }],
					isError: true,
					details: {},
				};
			}
		},
	});

		pi.registerCommand("wf", {
		description: "memento-workflow control (list | start <name> | status | cancel | reload | runs)",
		handler: async (args, ctx) => {
			const [sub, ...rest] = args.trim().split(/\s+/);
			const c = getClient();
			try {
				switch (sub) {
					case "":
					case "list": {
						const res = await c.call("list_workflows", { cwd: process.cwd() });
						const workflows = (res.workflows ?? []) as Array<{
							name: string;
							description: string;
							blocks: number;
						}>;
						if (workflows.length === 0) {
							ctx.ui.notify("no workflows discovered", "info");
							return;
						}
						const items = workflows.map((w) => `/${w.name}  (${w.blocks} blocks) — ${w.description}`);
						await ctx.ui.select("Available workflows", items);
						return;
					}
					case "start": {
						const name = rest[0];
						if (!name) {
							ctx.ui.notify("usage: /wf start <name>", "error");
							return;
						}
						await startWorkflow(name, c, ctx, pi, deps);
						return;
					}
					case "runs": {
						ctx.ui.notify("runs: not implemented yet", "info");
						return;
					}
					case "status": {
						const runId = rest[0] ?? getActive()?.runId;
						if (!runId) {
							ctx.ui.notify("usage: /wf status <run_id> (or start a workflow first)", "error");
							return;
						}
						const res = await c.call("status", { run_id: runId });
						ctx.ui.notify(JSON.stringify(res, null, 2), "info");
						return;
					}
					case "cancel": {
						const runId = rest[0] ?? getActive()?.runId;
						if (!runId) {
							ctx.ui.notify("nothing to cancel", "info");
							return;
						}
						abortActiveAutoRun("workflow cancelled");
						await c.call("cancel", { run_id: runId });
						setActive(null);
						updateWidget(ctx);
						ctx.ui.notify(`cancelled ${runId.slice(0, 12)}`, "info");
						return;
					}
					case "reload": {
						const hadActive = getActive();
						abortActiveAutoRun("workflow reload");
						setActive(null);
						updateWidget(ctx);
						if (client) {
							await client.shutdown();
							client = null;
						}
						getClient();
						const msg = hadActive
							? `reloaded python server (active run '${hadActive.workflowName}' dropped; use /wf resume to pick it up)`
							: "reloaded python server";
						ctx.ui.notify(msg, "info");
						return;
					}
					default:
						ctx.ui.notify(`unknown subcommand: ${sub}`, "error");
				}
			} catch (err) {
				ctx.ui.notify(`/wf ${sub} failed: ${(err as Error).message}`, "error");
			}
		},
		});

		pi.registerCommand("mw", {
			description: "memento workflow wrappers (create-protocol | process-protocol)",
			handler: async (args, ctx) => {
				const trimmed = args.trim();
				const splitAt = trimmed.indexOf(" ");
				const sub = trimmed ? (splitAt === -1 ? trimmed : trimmed.slice(0, splitAt)) : "";
				const rest = splitAt === -1 ? "" : trimmed.slice(splitAt + 1).trim();
				const c = getClient();
				try {
					switch (sub) {
						case "create-protocol": {
							const prepared = prepareCreateProtocol(rest, process.cwd());
							if (prepared.copiedPrdFrom) {
								ctx.ui.notify(`copied PRD into ${prepared.protocolDirDisplay}/prd.md`, "info");
							}
							await startWorkflow("create-protocol", c, ctx, pi, deps, {
								variables: {
									protocol_dir: toWorkflowPath(prepared.protocolDir, process.cwd()),
									prd_source: prepared.prdSource,
									workdir: process.cwd(),
								},
							});
							return;
						}
						case "process-protocol": {
							const protocolDir = await chooseProtocolDir(rest, ctx);
							ensurePlanExists(protocolDir);
							let resume = "";
							const lastRun = readLastRun(protocolDir);
							if (lastRun) {
								const ok = await ctx.ui.confirm(
									"process-protocol",
									`Found a previous run (${lastRun}). Resume it?`,
								);
								if (ok) resume = lastRun;
							}
							await startWorkflow("process-protocol", c, ctx, pi, deps, {
								variables: {
									protocol_dir: toWorkflowPath(protocolDir, process.cwd()),
								},
								resume,
							});
							return;
						}
						case "":
							ctx.ui.notify("usage: /mw <create-protocol | process-protocol> ...", "error");
							return;
						default:
							ctx.ui.notify(`unknown subcommand: ${sub}`, "error");
					}
				} catch (err) {
					ctx.ui.notify(`/mw ${sub} failed: ${(err as Error).message}`, "error");
				}
			},
		});
	};
}

export default createMementoExtension();
