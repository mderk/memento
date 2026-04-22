import {
	createAgent,
	createAgentSession,
	defaultStopCondition,
	type ExtensionAPI,
	type ExtensionContext,
	runAgent,
} from "@mariozechner/pi-coding-agent";
import type { MementoClient } from "./client.ts";
import { getConfig } from "./config.ts";
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
 *
 * Inline LLMSteps inside the child appear as `prompt` actions from _mw_next's
 * point of view — the relay LLM answers them in its own chat, honouring the
 * `isolation="inline"` contract. Nested subagent actions (leaf or relay) are
 * delegated via onNestedSubagent so we don't spin up tools inside tools.
 */
export async function runRelaySession(
	action: SubagentAction,
	pi: ExtensionAPI,
	ctx: ExtensionContext,
	client: MementoClient,
): Promise<RelayResult> {
	if (!action.child_run_id) {
		return {
			output: "",
			structured_output: null,
			error: "relay subagent action missing child_run_id",
			terminal: null,
		};
	}

	const modelSpec = resolveModelSpec(action.model);
	const [provider, id] = splitProvider(modelSpec);
	const model = ctx.modelRegistry.find(provider, id);
	if (!model) {
		return {
			output: "",
			structured_output: null,
			error: `model not found: ${modelSpec}`,
			terminal: null,
		};
	}
	const apiKey = ctx.modelRegistry.getApiKey(provider);
	if (!apiKey) {
		return {
			output: "",
			structured_output: null,
			error: `no api key for provider: ${provider}`,
			terminal: null,
		};
	}

	const allowedPiTools = resolveTools(pi, action.tools ?? null);

	const relayCtx: RelayToolsContext = {
		client,
		childRunId: action.child_run_id,
		ctx,
		onNestedSubagent: async (nested) => {
			if (nested.relay && nested.child_run_id) {
				const r = await runRelaySession(nested, pi, ctx, client);
				return { output: r.output, structured_output: r.structured_output, error: r.error };
			}
			return await runLLMStep(nested, pi, ctx);
		},
	};
	const relayTools = buildRelayTools(relayCtx);

	const session = createAgentSession({ tools: [...allowedPiTools, ...relayTools] });
	const agent = createAgent({ model, apiKey });

	session.appendMessage({
		role: "user",
		content: [{ type: "text", text: buildUserPrompt(action) }],
		timestamp: Date.now(),
	});

	try {
		await runAgent({
			agent,
			session,
			systemPrompt: buildSystemPrompt(action),
			signal: ctx.signal,
			stopWhen: defaultStopCondition,
			onUpdate: makePeekHandler(ctx),
		});
	} catch (err) {
		return {
			output: "",
			structured_output: null,
			error: `relay runAgent failed: ${(err as Error).message}`,
			terminal: relayCtx.terminal?.type ?? null,
		};
	}

	const finalText = extractFinalAssistantText(session);
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
}

function buildSystemPrompt(action: SubagentAction): string {
	const parts: string[] = [];
	parts.push(
		"You are a RELAY AGENT driving a child workflow run. Your job is to pump the workflow state machine until it terminates, not to solve the overall task yourself.",
	);
	parts.push(
		"Loop:\n" +
			"  1. Call _mw_next to pull the next action from the child run.\n" +
			"  2. If _mw_next returns a PROMPT, answer it in your own words (reading files, using tools as needed), then call _mw_submit with the matching exec_key.\n" +
			"  3. If _mw_next returns a terminal marker (completed/halted/error), stop the loop and emit your final summary message.\n" +
			"  4. Never invent exec_keys or run_ids — use exactly what _mw_next returned.\n" +
			"  5. For schema-backed prompts, put the JSON ONLY in structured_output of _mw_submit; leave its `output` empty.",
	);
	if (action.context_hint) {
		parts.push(`Context for this child run: ${action.context_hint}`);
	}
	parts.push(
		"When the child terminates, your FINAL assistant message should be a short summary of what the child run accomplished — this is what gets fed back to the parent workflow.",
	);
	return parts.join("\n\n");
}

function buildUserPrompt(action: SubagentAction): string {
	const parts: string[] = [];
	parts.push(action.prompt?.trim() || `Drive child workflow ${action.child_run_id} to completion.`);
	parts.push("Start by calling _mw_next.");
	return parts.join("\n\n");
}

function resolveModelSpec(blockModel: string | null | undefined): string {
	const cfg = getConfig();
	if (!blockModel) return cfg.defaultModel;
	const alias = cfg.models[blockModel.toLowerCase()];
	if (alias) return alias;
	return blockModel;
}

function splitProvider(spec: string): [string, string] {
	if (spec.includes("/")) {
		const slash = spec.indexOf("/");
		return [spec.slice(0, slash), spec.slice(slash + 1)];
	}
	return [getConfig().defaultProvider, spec];
}

function resolveTools(pi: ExtensionAPI, allowed: string[] | null): ReturnType<ExtensionAPI["getAllTools"]> {
	const all = pi.getAllTools();
	if (!allowed || allowed.length === 0) return all;
	const wanted = new Set(allowed.map((s) => s.toLowerCase()));
	return all.filter((t) => wanted.has(t.name.toLowerCase()));
}

function extractFinalAssistantText(session: ReturnType<typeof createAgentSession>): string {
	const entries = session.getEntries();
	for (let i = entries.length - 1; i >= 0; i--) {
		const e = entries[i] as { type?: string; role?: string; content?: unknown };
		if (e.type !== "message" || e.role !== "assistant") continue;
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
