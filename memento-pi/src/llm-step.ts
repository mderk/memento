import { readFileSync } from "node:fs";
import {
	createAgent,
	createAgentSession,
	defaultStopCondition,
	type ExtensionAPI,
	type ExtensionContext,
	runAgent,
} from "@mariozechner/pi-coding-agent";
import { getConfig } from "./config.ts";
import { makePeekHandler } from "./peek.ts";
import type { SubagentAction } from "./types.ts";

export interface LLMStepResult {
	output: string;
	structured_output: unknown;
	error?: string;
}

/**
 * Run a subagent-isolation LLMStep in an isolated pi sub-session.
 * Returns the text + parsed-JSON structured_output (if the final assistant text is JSON).
 */
export async function runLLMStep(
	action: SubagentAction,
	pi: ExtensionAPI,
	ctx: ExtensionContext,
): Promise<LLMStepResult> {
	const modelSpec = resolveModelSpec(action.model);
	const [provider, id] = splitProvider(modelSpec);
	const model = ctx.modelRegistry.find(provider, id);
	if (!model) {
		return {
			output: "",
			structured_output: null,
			error: `model not found: ${modelSpec}`,
		};
	}

	const apiKey = ctx.modelRegistry.getApiKey(provider);
	if (!apiKey) {
		return {
			output: "",
			structured_output: null,
			error: `no api key for provider: ${provider}`,
		};
	}

	const tools = resolveTools(pi, action.tools ?? null);

	const promptText = resolvePromptText(action);

	const session = createAgentSession({ tools });
	const agent = createAgent({ model, apiKey });

	session.appendMessage({
		role: "user",
		content: [{ type: "text", text: promptText }],
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
			error: `runAgent failed: ${(err as Error).message}`,
		};
	}

	const finalText = extractFinalAssistantText(session);
	const structured = tryParseJson(finalText);

	if (structured !== undefined) {
		return { output: "", structured_output: structured };
	}
	return { output: finalText, structured_output: null };
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

function resolvePromptText(action: SubagentAction): string {
	return action.prompt ?? "";
}

function buildSystemPrompt(action: SubagentAction): string {
	const parts: string[] = [];
	parts.push("You are running a single focused task inside an isolated workflow step.");
	if (action.context_hint) {
		parts.push(`Context: ${action.context_hint}`);
	}
	parts.push(
		"If the task specifies a structured output (JSON / schema), your FINAL assistant message must be the JSON object itself, with nothing else around it (no markdown fence, no commentary).",
	);
	parts.push("If no structured output is specified, keep your final message short and to the point.");
	return parts.join("\n\n");
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

// Keep readFileSync import path reserved for future use when we want to inline
// prompt_file contents on the subagent side (currently engine returns fully
// substituted `prompt` text in SubagentAction.prompt).
void readFileSync;
