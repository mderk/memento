export interface ActionBase {
	action: string;
	run_id: string;
	protocol_version?: number;
	_display?: string;
	_shell_log?: Array<Record<string, unknown>>;
	warnings?: string[];
	_resumed?: boolean;
}

export interface PromptAction extends ActionBase {
	action: "prompt";
	exec_key: string;
	prompt: string;
	prompt_file?: string;
	prompt_hash?: string;
	tools?: string[];
	model?: string;
	json_schema?: Record<string, unknown>;
	schema_file?: string;
	schema_id?: string;
	output_schema_name?: string;
	context_files?: string[];
	result_dir?: string;
}

export interface AskUserAction extends ActionBase {
	action: "ask_user";
	exec_key: string;
	prompt_type: "confirm" | "choice" | "input" | string;
	message: string;
	options?: string[] | null;
	default?: string | null;
	strict?: boolean | null;
	result_var?: string | null;
	_retry_confirm?: boolean;
}

export interface SubagentAction extends ActionBase {
	action: "subagent";
	exec_key: string;
	prompt: string;
	relay?: boolean;
	child_run_id?: string;
	context_hint?: string;
	tools?: string[];
	model?: string;
}

export interface ParallelAction extends ActionBase {
	action: "parallel";
	exec_key: string;
	lanes: Array<{ child_run_id: string; exec_key: string; prompt: string; relay?: boolean }>;
	model?: string;
}

export interface CompletedAction extends ActionBase {
	action: "completed";
	summary: Record<string, unknown>;
	totals: Record<string, unknown>;
}

export interface HaltedAction extends ActionBase {
	action: "halted";
	reason: string;
	halted_at: string;
}

export interface ErrorAction extends ActionBase {
	action: "error";
	message: string;
	exec_key?: string;
	expected_exec_key?: string;
	got?: string;
}

export interface CancelledAction extends ActionBase {
	action: "cancelled";
}

export type TerminalAction = CompletedAction | HaltedAction | ErrorAction | CancelledAction;
export type WorkflowAction =
	| PromptAction
	| AskUserAction
	| SubagentAction
	| ParallelAction
	| TerminalAction;

export function isTerminal(a: ActionBase): a is TerminalAction {
	return a.action === "completed" || a.action === "halted" || a.action === "error" || a.action === "cancelled";
}
