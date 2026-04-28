import type {
	AskUserAction,
	ParallelAction,
	PromptAction,
	SubagentAction,
	TerminalAction,
	WorkflowAction,
} from "./types.ts";

export type RunMode = "idle" | "handoff" | "awaiting-user" | "auto-running";
export type PendingAction = PromptAction | AskUserAction | SubagentAction | ParallelAction;
export type ActiveRunMode = Exclude<RunMode, "idle">;

export interface ActiveRun {
	runId: string;
	workflowName: string;
	mode: ActiveRunMode;
	pending: PendingAction;
	stepCount: number;
	lastTerminal?: TerminalAction;
	peek?: string;
	autoRunController?: AbortController;
}

const STATE_KEY = "__memento_pi_state__";
interface GlobalState {
	active: ActiveRun | null;
}
function gs(): GlobalState {
	const g = globalThis as Record<string, unknown>;
	if (!g[STATE_KEY]) g[STATE_KEY] = { active: null };
	return g[STATE_KEY] as GlobalState;
}

export function getActive(): ActiveRun | null {
	return gs().active;
}

export function setActive(run: ActiveRun | null): void {
	process.stderr.write(
		`[mw] setActive: ${run ? `${run.runId}/${run.pending.exec_key} mode=${run.mode}` : "null"}\n`,
	);
	gs().active = run;
}

export function abortActiveAutoRun(reason?: string): void {
	const run = gs().active;
	const controller = run?.autoRunController;
	if (!controller) return;
	if (!controller.signal.aborted) controller.abort(reason);
	if (run) run.autoRunController = undefined;
}

export function setPeek(text: string): void {
	const a = gs().active;
	if (!a) return;
	a.peek = text;
}

export function clearPeek(): void {
	const a = gs().active;
	if (!a) return;
	a.peek = undefined;
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
	return "unknown";
}
