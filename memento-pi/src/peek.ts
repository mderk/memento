import { setPeek } from "./state.ts";
import { updateWidget } from "./widget.ts";
import type { ExtensionContext } from "@mariozechner/pi-coding-agent";

/**
 * Build an onUpdate handler for runAgent that mirrors the last bit of
 * assistant activity into the widget's peek line. Intentionally defensive —
 * the pi onUpdate event shape is not strictly typed here, so we try a handful
 * of common fields before giving up quietly.
 */
export function makePeekHandler(ctx: ExtensionContext): (event: unknown) => void {
	let lastWrite = 0;
	return (event: unknown) => {
		const text = extractText(event);
		if (!text) return;
		const now = Date.now();
		if (now - lastWrite < 120) return;
		lastWrite = now;
		setPeek(text);
		updateWidget(ctx);
	};
}

function extractText(event: unknown): string | null {
	if (!event || typeof event !== "object") return null;
	const e = event as Record<string, unknown>;

	const type = typeof e.type === "string" ? e.type : "";

	if (type === "tool_start" || type === "tool_call_start") {
		const name = typeof e.name === "string" ? e.name : (e.toolName as string | undefined) ?? "tool";
		return `→ ${name}`;
	}
	if (type === "tool_end" || type === "tool_call_end") {
		const name = typeof e.name === "string" ? e.name : (e.toolName as string | undefined) ?? "tool";
		return `✓ ${name}`;
	}

	const deltaText = pick(e, ["delta", "text", "content", "chunk", "message"]);
	if (typeof deltaText === "string" && deltaText.trim()) return deltaText;

	if (Array.isArray(e.content)) {
		for (const part of e.content) {
			if (part && typeof part === "object") {
				const t = (part as { type?: string; text?: string }).text;
				if (typeof t === "string" && t.trim()) return t;
			}
		}
	}

	return null;
}

function pick(obj: Record<string, unknown>, keys: string[]): unknown {
	for (const k of keys) {
		if (k in obj) return obj[k];
	}
	return undefined;
}
