import { readFileSync } from "node:fs";
import {
	createAgentSession,
	type ExtensionAPI,
	type ExtensionContext,
	SessionManager,
} from "@mariozechner/pi-coding-agent";
import { getConfig, resolveModelSelection } from "./config.ts";
import { makePeekHandler } from "./peek.ts";
import type { SubagentAction } from "./types.ts";

export interface LLMStepResult {
	output: string;
	structured_output: unknown;
	error?: string;
}

export async function runAgentPrompt(
	promptText: string,
	pi: ExtensionAPI,
	ctx: ExtensionContext,
	options: {
		model?: string | null;
		tools?: string[] | null;
		signal?: AbortSignal;
		parseJson?: boolean;
	} = {},
): Promise<LLMStepResult> {
	const modelSelection = resolveModelSelection(options.model);
	const [provider, id] = splitProvider(modelSelection.spec);
	const model = ctx.modelRegistry.find(provider, id);
	if (!model) {
		return {
			output: "",
			structured_output: null,
			error: `model not found: ${modelSelection.spec}`,
		};
	}

	const toolNames = resolveToolNames(pi, options.tools ?? null);

	try {
		const { session } = await createAgentSession({
			cwd: ctx.cwd,
			model,
			thinkingLevel: modelSelection.thinkingLevel,
			modelRegistry: ctx.modelRegistry,
			tools: toolNames,
			sessionManager: SessionManager.inMemory(ctx.cwd),
		});

		session.subscribe((event) => makePeekHandler(ctx)(event));
		const signal = options.signal;
		if (signal) {
			if (signal.aborted) return { output: "", structured_output: null, error: "run aborted" };
			signal.addEventListener("abort", () => {
				void session.abort();
			}, { once: true });
		}

		await session.prompt(promptText);

		const finalText = extractFinalAssistantText(session.messages);
		const structured = options.parseJson === false ? undefined : tryParseJson(finalText);
		if (structured !== undefined) return { output: "", structured_output: structured };
		return { output: finalText, structured_output: null };
	} catch (err) {
		return {
			output: "",
			structured_output: null,
			error: `runAgent failed: ${(err as Error).message}`,
		};
	}
}

/**
 * Run a subagent-isolation LLMStep in an isolated pi sub-session.
 * Returns the text + parsed-JSON structured_output (if the final assistant text is JSON).
 */
export async function runLLMStep(
	action: SubagentAction,
	pi: ExtensionAPI,
	ctx: ExtensionContext,
	signal?: AbortSignal,
): Promise<LLMStepResult> {
	return await runAgentPrompt(resolvePromptText(action), pi, ctx, {
		model: action.model,
		tools: action.tools ?? null,
		signal,
	});
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

function resolvePromptText(action: SubagentAction): string {
	return action.prompt ?? "";
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

// Keep readFileSync import path reserved for future use when we want to inline
// prompt_file contents on the subagent side (currently engine returns fully
// substituted `prompt` text in SubagentAction.prompt).
void readFileSync;
