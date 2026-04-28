import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { MementoClient } from "../../src/client.ts";
import { createMementoExtension } from "../../src/index.ts";
import type { ClientLike } from "../../src/runtime.ts";
import { getActive, setActive } from "../../src/state.ts";
import type { LLMStepResult } from "../../src/llm-step.ts";
import type { RelayResult } from "../../src/relay-session.ts";
import type { Scenario, ScenarioStep } from "./scenario.ts";
import { matchScenarioStep, resolveWorkflowDirs } from "./scenario.ts";

interface ServerConfigLike {
	cwd: string;
	command: string;
	args: string[];
}

export class RestartableClient implements ClientLike {
	private inner: MementoClient;
	private readonly config: ServerConfigLike;

	constructor(config: ServerConfigLike) {
		this.config = config;
		this.inner = new MementoClient(config);
	}

	call(method: string, params: Record<string, unknown> = {}): Promise<any> {
		return this.inner.call(method, params);
	}

	async shutdown(): Promise<void> {
		await this.inner.shutdown();
	}

	async restartAndResume(opts: {
		workflow: string;
		cwd: string;
		workflowDirs: string[];
		runId: string;
	}): Promise<any> {
		await this.inner.shutdown();
		this.inner = new MementoClient(this.config);
		return await this.call("start", {
			workflow: opts.workflow,
			cwd: opts.cwd,
			workflow_dirs: opts.workflowDirs,
			resume: opts.runId,
		});
	}
}

export class FakeUI {
	notifications: Array<{ message: string; type?: string }> = [];
	widgets: Array<{ key: string; content: string[] | undefined }> = [];
	statuses: Array<{ key: string; text: string | undefined }> = [];
	selectCalls: string[] = [];
	confirmCalls: string[] = [];
	inputCalls: string[] = [];
	private execKeyOverride: string | null = null;
	private interactionIndex = new Map<string, number>();
	private readonly scenario: Scenario;

	constructor(scenario: Scenario) { this.scenario = scenario; }

	async select(title: string, options: string[]): Promise<string | undefined> {
		this.selectCalls.push(title);
		const step = this.stepForCurrentExecKey();
		const interaction = this.nextInteraction(step, "choice");
		if (interaction) return interaction.answer;
		const output = step.submit.output;
		assert.equal(typeof output, "string", `select answer for ${step.match} must be string`);
		assert.ok(options.includes(output), `select answer '${output}' not in options ${options.join(", ")}`);
		return output;
	}

	async confirm(_title: string, message: string): Promise<boolean> {
		this.confirmCalls.push(message);
		const step = this.stepForCurrentExecKey();
		const interaction = this.nextInteraction(step, "confirm");
		const answer = interaction?.answer ?? step.submit.output;
		assert.equal(typeof answer, "string", `confirm answer for ${step.match} must be string`);
		return answer !== "no";
	}

	async input(_title: string, placeholder?: string): Promise<string | undefined> {
		this.inputCalls.push(placeholder ?? "");
		const step = this.stepForCurrentExecKey();
		const interaction = this.nextInteraction(step, "input");
		const answer = interaction?.answer ?? step.submit.output;
		assert.equal(typeof answer, "string", `input answer for ${step.match} must be string`);
		return answer;
	}

	notify(message: string, type?: "info" | "warning" | "error"): void {
		this.notifications.push({ message, type });
	}

	onTerminalInput(): () => void {
		return () => {};
	}

	setStatus(key: string, text: string | undefined): void {
		this.statuses.push({ key, text });
	}

	setWorkingMessage(): void {}
	setWorkingIndicator(): void {}
	setHiddenThinkingLabel(): void {}
	setWidget(key: string, content: string[] | undefined): void {
		this.widgets.push({ key, content });
	}
	setFooter(): void {}
	setHeader(): void {}
	setTitle(): void {}
	async custom(): Promise<never> { throw new Error("custom UI not implemented in tests"); }
	pasteToEditor(): void {}
	setEditorText(): void {}
	getEditorText(): string { return ""; }
	async editor(): Promise<string | undefined> { return undefined; }
	setEditorComponent(): void {}
	get theme(): any { return {}; }
	getAllThemes(): any[] { return []; }
	getTheme(): any { return undefined; }
	setTheme(): { success: boolean; error?: string } { return { success: true }; }
	getToolsExpanded(): boolean { return false; }
	setToolsExpanded(): void {}

	async withExecKeyOverride<T>(execKey: string, fn: () => Promise<T>): Promise<T> {
		const prev = this.execKeyOverride;
		this.execKeyOverride = execKey;
		try {
			return await fn();
		} finally {
			this.execKeyOverride = prev;
		}
	}

	private stepForCurrentExecKey(): ScenarioStep {
		const execKey = this.execKeyOverride ?? getActive()?.pending.exec_key;
		assert.ok(execKey, "No active exec_key available for fake UI answer");
		return matchScenarioStep(this.scenario, execKey);
	}

	private nextInteraction(step: ScenarioStep, kind: "choice" | "confirm" | "input") {
		const list = step.interactions?.filter((i) => i.ui === kind) ?? [];
		if (list.length === 0) return undefined;
		const key = `${step.match}:${kind}`;
		const idx = this.interactionIndex.get(key) ?? 0;
		this.interactionIndex.set(key, idx + 1);
		return list[idx];
	}
}

export class FakePi {
	private events = new Map<string, Array<(...args: any[]) => any>>();
	private tools = new Map<string, any>();
	private commands = new Map<string, any>();
	messages: Array<{ text: string; opts?: unknown }> = [];

	on(name: string, handler: (...args: any[]) => any): void {
		const list = this.events.get(name) ?? [];
		list.push(handler);
		this.events.set(name, list);
	}

	registerTool(def: any): void {
		this.tools.set(def.name, def);
	}

	registerCommand(name: string, def: any): void {
		this.commands.set(name, def);
	}

	getAllTools(): any[] {
		return Array.from(this.tools.values());
	}

	sendUserMessage(text: string, opts?: unknown): void {
		this.messages.push({ text, opts });
	}

	async trigger(name: string, event: any, ctx?: any): Promise<any> {
		let last: any;
		for (const handler of this.events.get(name) ?? []) {
			last = await handler(event, ctx);
		}
		return last;
	}

	async runCommand(name: string, args: string, ctx: any): Promise<void> {
		const cmd = this.commands.get(name);
		assert.ok(cmd, `command '${name}' not registered`);
		await cmd.handler(args, ctx);
	}

	async runTool(name: string, params: Record<string, unknown>, ctx: any): Promise<any> {
		const tool = this.tools.get(name);
		assert.ok(tool, `tool '${name}' not registered`);
		return await tool.execute("tool-call", params, undefined, undefined, ctx);
	}
}

export function createFakeContext(cwd: string, ui: FakeUI): any {
	return {
		ui,
		hasUI: true,
		cwd,
		sessionManager: {},
		modelRegistry: { find: () => undefined },
		model: undefined,
		isIdle: () => true,
		signal: undefined,
		abort: () => {},
		hasPendingMessages: () => false,
		shutdown: () => {},
		getContextUsage: () => undefined,
		compact: () => {},
		getSystemPrompt: () => "SYSTEM",
	};
}

export async function runScenarioThroughExtension(scenario: Scenario): Promise<{
	ui: FakeUI;
	pi: FakePi;
	handoffExecKeys: string[];
	restartEvents: Array<{ scope: string; exec_key: string }>;
	tmpCwd: string;
}> {
	setActive(null);
	const workflowEngineDir = resolve(import.meta.dirname, "../../../memento-workflow");
	const tmpCwd = mkdtempSync(resolve(tmpdir(), "memento-pi-it-"));
	const oldCwd = process.cwd();
	const oldEnv = process.env.MEMENTO_WORKFLOW_DIR;
	process.env.MEMENTO_WORKFLOW_DIR = workflowEngineDir;
	process.chdir(tmpCwd);

	const serverConfig = {
		cwd: workflowEngineDir,
		command: "uv",
		args: ["run", "python", "-m", "scripts.server"],
	};
	const client = new RestartableClient(serverConfig);
	const restartEvents: Array<{ scope: string; exec_key: string }> = [];
	const usedRestarts = new Set<string>();
	const resolvedWorkflowDirs = resolveWorkflowDirs(scenario);
	const ui = new FakeUI(scenario);
	const ctx = createFakeContext(tmpCwd, ui);
	const pi = new FakePi();
	const handoffExecKeys: string[] = [];

	const findSubmit = (execKey: string): Record<string, unknown> => {
		const step = matchScenarioStep(scenario, execKey);
		return { ...step.submit };
	};

	const maybeRunInteractions = async (execKey: string): Promise<void> => {
		const step = matchScenarioStep(scenario, execKey);
		for (const interaction of step.interactions ?? []) {
			await ui.withExecKeyOverride(execKey, async () => {
				if (interaction.ui === "choice") {
					await ui.select(`interaction:${execKey}`, [interaction.answer]);
				} else if (interaction.ui === "confirm") {
					await ui.confirm("interaction", `interaction:${execKey}`);
				} else {
					await ui.input("interaction", `interaction:${execKey}`);
				}
			});
		}
	};

	const maybeRestartRelay = async (rootExecKey: string, childExecKey: string, rootRunId: string, childRunId: string) => {
		for (const rp of scenario.restarts ?? []) {
			const key = `${rp.scope}:${rp.afterExecKey}`;
			if (usedRestarts.has(key)) continue;
			if (rp.scope === "relay-child" && rp.afterExecKey === childExecKey) {
				usedRestarts.add(key);
				restartEvents.push({ scope: rp.scope, exec_key: childExecKey });
				const resumed = await client.restartAndResume({
					workflow: scenario.workflow,
					cwd: tmpCwd,
					workflowDirs: resolvedWorkflowDirs,
					runId: rootRunId,
				});
				assert.equal(resumed.action, "subagent");
				assert.equal(resumed.exec_key, rootExecKey);
				assert.equal(resumed.child_run_id, childRunId);
			}
		}
	};

	const runRelay = async (action: any): Promise<RelayResult> => {
		assert.ok(action.child_run_id, "relay action missing child_run_id");
		while (true) {
			const next = await client.call("next", { run_id: action.child_run_id });
			if (next.action === "completed") {
				return { output: `relay child ${action.child_run_id} completed`, structured_output: null, terminal: "completed" };
			}
			if (next.action === "halted") {
				return { output: "", structured_output: null, error: next.reason, terminal: "halted" };
			}
			if (next.action === "error" || next.action === "cancelled") {
				return { output: "", structured_output: null, error: next.message ?? next.action, terminal: next.action };
			}
			assert.equal(next.action, "prompt", `unexpected relay child action ${next.action}`);
			await maybeRunInteractions(next.exec_key);
			const submit = findSubmit(next.exec_key);
			await client.call("submit", {
				run_id: action.child_run_id,
				exec_key: next.exec_key,
				output: submit.output ?? "",
				structured_output: submit.structured_output ?? null,
				status: submit.status ?? "success",
				error: null,
			});
			await maybeRestartRelay(action.exec_key, next.exec_key, action.run_id, action.child_run_id);
		}
	};

	const runLeaf = async (action: any): Promise<LLMStepResult> => {
		await maybeRunInteractions(action.exec_key);
		const submit = findSubmit(action.exec_key);
		return {
			output: typeof submit.output === "string" ? submit.output : "",
			structured_output: submit.structured_output ?? null,
		};
	};

	const extension = createMementoExtension({
		resolveServerConfig: () => serverConfig,
		createClient: () => client,
		runRelaySession: async (action) => await runRelay(action),
		runLLMStep: async (action) => await runLeaf(action),
	});
	extension(pi as unknown as ExtensionAPI);

	try {
		await pi.trigger("session_start", {}, ctx);
		await pi.runCommand("wf", `start ${scenario.workflow}`, ctx);

		while (true) {
			const active = getActive();
			if (!active) break;
			assert.equal(active.mode, "handoff", `expected handoff mode, got ${active.mode}`);
			assert.equal(active.pending.action, "prompt");
			handoffExecKeys.push(active.pending.exec_key);
			const injected = await pi.trigger("before_agent_start", { systemPrompt: "BASE" }, ctx);
			assert.ok(injected?.systemPrompt?.includes(`<workflow-pending>`));
			assert.ok(injected.systemPrompt.includes(`exec_key: ${active.pending.exec_key}`));
			const submit = findSubmit(active.pending.exec_key);
			const toolResult = await pi.runTool("workflow_submit", {
				run_id: active.runId,
				exec_key: active.pending.exec_key,
				output: submit.output,
				structured_output: submit.structured_output,
			}, ctx);
			assert.notEqual(toolResult.isError, true, JSON.stringify(toolResult));
		}
		await pi.trigger("session_shutdown", {}, ctx);
		return { ui, pi, handoffExecKeys, restartEvents, tmpCwd };
	} finally {
		try {
			await client.shutdown();
		} catch {
			// ignore double shutdown in tests
		}
		setActive(null);
		process.chdir(oldCwd);
		if (oldEnv == null) delete process.env.MEMENTO_WORKFLOW_DIR;
		else process.env.MEMENTO_WORKFLOW_DIR = oldEnv;
	}
}
