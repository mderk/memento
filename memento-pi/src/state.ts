import type { PromptAction, SubagentAction, TerminalAction, WorkflowAction } from "./types.ts";

export type PendingAction = PromptAction | SubagentAction;

export interface ActiveRun {
	runId: string;
	workflowName: string;
	pending: PendingAction;
	stepCount: number;
	lastTerminal?: TerminalAction;
	peek?: string;
}

let active: ActiveRun | null = null;

export function getActive(): ActiveRun | null {
	return active;
}

export function setActive(run: ActiveRun | null): void {
	active = run;
}

export function setPeek(text: string): void {
	if (!active) return;
	active.peek = text;
}

export function clearPeek(): void {
	if (!active) return;
	active.peek = undefined;
}

export function describeAction(a: WorkflowAction): string {
	if (a.action === "prompt") return `prompt ${a.exec_key}`;
	if (a.action === "ask_user") return `ask_user ${a.exec_key}`;
	if (a.action === "subagent") return `subagent ${a.exec_key}`;
	if (a.action === "parallel") return `parallel ${a.exec_key}`;
	if (a.action === "completed") return "completed";
	if (a.action === "halted") return `halted: ${a.reason}`;
	if (a.action === "error") return `error: ${a.message}`;
	if (a.action === "cancelled") return "cancelled";
	return a.action;
}
