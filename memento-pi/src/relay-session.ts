import {
	createAgentSession,
	type ExtensionAPI,
	type ExtensionContext,
	SessionManager,
} from "@mariozechner/pi-coding-agent";
import { getConfig, resolveModelSelection } from "./config.ts";
import type { ClientLike } from "./runtime.ts";
import { runLLMStep } from "./llm-step.ts";
import { buildRelayTools, type RelayToolsContext } from "./mw-tools.ts";
import { makePeekHandler } from "./peek.ts";
import type { SubagentAction } from "./types.ts";

export interface RelayResult {
	output: string;
	structured_output: unknown;
	error?: string;
	terminal: "completed" | "halted" | "error" | "cancelled" | null;
}

/**
 * Drive a SubagentAction(relay=true, child_run_id=X) in a real pi sub-session
 * that acts as the relay agent. The sub-session gets _mw_next/_mw_submit/_mw_status
 * tools bound to the child run, plus any allow-listed pi tools.
 */
export async function runRelaySession(
	action: SubagentAction,
	pi: ExtensionAPI,
	ctx: ExtensionContext,
	client: ClientLike,
	signal?: AbortSignal,
): Promise<RelayResult> {
	if (!action.child_run_id) {
		return {
			output: "",
			structured_output: null,
			error: "relay subagent action missing child_run_id",
			terminal: null,
		};
	}

	const modelSelection = resolveModelSelection(action.model);
	const [provider, id] = splitProvider(modelSelection.spec);
	const model = ctx.modelRegistry.find(provider, id);
	if (!model) {
		return {
			output: "",
			structured_output: null,
			error: `model not found: ${modelSelection.spec}`,
			terminal: null,
		};
	}

	const allowedToolNames = resolveToolNames(pi, action.tools ?? null);

	const relayCtx: RelayToolsContext = {
		client,
		childRunId: action.child_run_id,
		ctx,
		onNestedSubagent: async (nested) => {
			if (nested.relay && nested.child_run_id) {
				const r = await runRelaySession(nested, pi, ctx, client, signal);
				return { output: r.output, structured_output: r.structured_output, error: r.error };
			}
			return await runLLMStep(nested, pi, ctx, signal);
		},
	};
	const relayTools = buildRelayTools(relayCtx);

	try {
		const { session } = await createAgentSession({
			cwd: ctx.cwd,
			model,
			thinkingLevel: modelSelection.thinkingLevel,
			modelRegistry: ctx.modelRegistry,
			tools: [...allowedToolNames, ...relayTools.map((t) => t.name)],
			customTools: relayTools,
			sessionManager: SessionManager.inMemory(ctx.cwd),
		});

		session.subscribe((event) => makePeekHandler(ctx)(event));
		if (signal) {
			if (signal.aborted) {
				return { output: "", structured_output: null, error: "relay run aborted", terminal: null };
			}
			signal.addEventListener(
				"abort",
				() => {
					void session.abort();
				},
				{ once: true },
			);
		}

		await session.prompt(buildUserPrompt(action));

		const finalText = extractFinalAssistantText(session.messages);
		const structured = tryParseJson(finalText);

		const terminalType = relayCtx.terminal?.type ?? null;
		if (terminalType && terminalType !== "completed") {
			return {
				output: finalText,
				structured_output: structured ?? null,
				error: `child workflow ${terminalType}`,
				terminal: terminalType,
			};
		}
		if (!terminalType) {
			return {
				output: finalText,
				structured_output: structured ?? null,
				error: "relay agent stopped before child workflow terminated",
				terminal: null,
			};
		}

		if (structured !== undefined) {
			return { output: "", structured_output: structured, terminal: terminalType };
		}
		return { output: finalText, structured_output: null, terminal: terminalType };
	} catch (err) {
		return {
			output: "",
			structured_output: null,
			error: `relay runAgent failed: ${(err as Error).message}`,
			terminal: relayCtx.terminal?.type ?? null,
		};
	}
}

function buildUserPrompt(action: SubagentAction): string {
	const parts: string[] = [];
	parts.push(action.prompt?.trim() || `Drive child workflow ${action.child_run_id} to completion.`);
	parts.push("Start by calling _mw_next.");
	return parts.join("\n\n");
}

function splitProvider(spec: string): [string, string] {
	if (spec.includes("/")) {
		const slash = spec.indexOf("/");
		return [spec.slice(0, slash), spec.slice(slash + 1)];
	}
	return [getConfig().defaultProvider, spec];
}

function resolveToolNames(pi: ExtensionAPI, allowed: string[] | null): string[] {
	const allNames = pi.getAllTools().map((t) => t.name);
	if (!allowed || allowed.length === 0) return allNames;
	const wanted = new Set(allowed.map((s) => s.toLowerCase()));
	return allNames.filter((name) => wanted.has(name.toLowerCase()));
}

function extractFinalAssistantText(messages: readonly unknown[]): string {
	for (let i = messages.length - 1; i >= 0; i--) {
		const e = messages[i] as { role?: string; content?: unknown };
		if (e.role !== "assistant") continue;
		const content = e.content;
		if (!Array.isArray(content)) continue;
		const texts: string[] = [];
		for (const part of content) {
			if (part && typeof part === "object" && (part as { type?: string }).type === "text") {
				const t = (part as { text?: string }).text;
				if (typeof t === "string") texts.push(t);
			}
		}
		if (texts.length > 0) return texts.join("\n").trim();
	}
	return "";
}

function tryParseJson(text: string): unknown | undefined {
	if (!text) return undefined;
	const trimmed = stripJsonFence(text);
	try {
		const parsed = JSON.parse(trimmed);
		if (parsed && typeof parsed === "object") return parsed;
	} catch {
		/* not JSON */
	}
	return undefined;
}

function stripJsonFence(s: string): string {
	const t = s.trim();
	if (t.startsWith("```")) {
		const firstNl = t.indexOf("\n");
		const lastFence = t.lastIndexOf("```");
		if (firstNl !== -1 && lastFence > firstNl) {
			return t.slice(firstNl + 1, lastFence).trim();
		}
	}
	return t;
}
