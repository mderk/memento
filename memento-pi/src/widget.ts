import type { ExtensionContext } from "@mariozechner/pi-coding-agent";
import { getActive } from "./state.ts";

const WIDGET_ID = "memento";
const PEEK_MAX = 160;

export function updateWidget(ctx: ExtensionContext): void {
	const run = getActive();
	if (!run) {
		ctx.ui.setWidget(WIDGET_ID, []);
		ctx.ui.setStatus(WIDGET_ID, "");
		return;
	}
	const short = run.runId.length > 12 ? run.runId.slice(0, 12) : run.runId;
	const lines = [
		`▶ ${run.workflowName} · ${short}`,
		`step ${run.stepCount} · ${run.pending.exec_key}`,
	];
	if (run.peek) {
		lines.push(`  └ ${truncate(run.peek, PEEK_MAX)}`);
	}
	ctx.ui.setWidget(WIDGET_ID, lines);
	ctx.ui.setStatus(WIDGET_ID, `wf:${run.workflowName}[${run.pending.exec_key}]`);
}

function truncate(s: string, max: number): string {
	const flat = s.replace(/\s+/g, " ").trim();
	if (flat.length <= max) return flat;
	return `${flat.slice(0, max - 1)}…`;
}
