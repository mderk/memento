import test from "node:test";
import assert from "node:assert/strict";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { createMementoExtension } from "../src/index.ts";
import { getActive, setActive } from "../src/state.ts";
import { RestartableClient, FakePi, createFakeContext } from "./helpers/harness.ts";

class SimpleUI {
	notifications: Array<{ message: string; type?: string }> = [];
	confirmCalls: string[] = [];
	widgets: Array<{ key: string; content: string[] | undefined }> = [];
	statuses: Array<{ key: string; text: string | undefined }> = [];

	async select(_title: string, options: string[]): Promise<string | undefined> {
		return options[0];
	}

	async confirm(_title: string, message: string): Promise<boolean> {
		this.confirmCalls.push(message);
		return true;
	}

	async input(): Promise<string | undefined> {
		return undefined;
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
}

const REPO_ROOT = resolve(import.meta.dirname, "../..");
const WORKFLOW_ENGINE_DIR = resolve(REPO_ROOT, "memento-workflow");

function copyWorkflow(tmpCwd: string, name: string): void {
	const src = resolve(REPO_ROOT, ".workflows", name);
	const dst = join(tmpCwd, ".workflows", name);
	mkdirSync(join(tmpCwd, ".workflows"), { recursive: true });
	cpSync(src, dst, { recursive: true });
}

async function withExtension<T>(
	tmpCwd: string,
	deps: Parameters<typeof createMementoExtension>[0],
	run: (ctx: any, ui: SimpleUI, pi: FakePi) => Promise<T>,
): Promise<T> {
	setActive(null);
	const oldCwd = process.cwd();
	const oldEnv = process.env.MEMENTO_WORKFLOW_DIR;
	process.chdir(tmpCwd);
	process.env.MEMENTO_WORKFLOW_DIR = WORKFLOW_ENGINE_DIR;

	const serverConfig = {
		cwd: WORKFLOW_ENGINE_DIR,
		command: "uv",
		args: ["run", "python", "-m", "scripts.server"],
	};
	const client = new RestartableClient(serverConfig);
	const ui = new SimpleUI();
	const ctx = createFakeContext(tmpCwd, ui);
	const pi = new FakePi();
	createMementoExtension({
		resolveServerConfig: () => serverConfig,
		createClient: () => client,
		...deps,
	})(pi as unknown as ExtensionAPI);

	try {
		await pi.trigger("session_start", {}, ctx);
		return await run(ctx, ui, pi);
	} finally {
		try {
			await pi.trigger("session_shutdown", {}, ctx);
		} catch {
			// ignore
		}
		try {
			await client.shutdown();
		} catch {
			// ignore
		}
		setActive(null);
		process.chdir(oldCwd);
		if (oldEnv == null) delete process.env.MEMENTO_WORKFLOW_DIR;
		else process.env.MEMENTO_WORKFLOW_DIR = oldEnv;
	}
}

test("/mw create-protocol starts real workflow and renders protocol files", async () => {
	const tmpCwd = mkdtempSync(join(tmpdir(), "memento-pi-create-"));
	copyWorkflow(tmpCwd, "create-protocol");
	copyWorkflow(tmpCwd, "process-protocol");

	await withExtension(
		tmpCwd,
		{
			async runRelaySession() {
				throw new Error("relay session should not be used in create-protocol smoke test");
			},
			async runLLMStep(action) {
				if (action.exec_key === "ensure-prd") {
					return {
						output: "",
						structured_output: {
							title: "Dogfood protocol",
							problem_statement: "Need a real protocol smoke path in pi.",
							requirements: ["Generate protocol files"],
							constraints: ["Keep workflow definitions unchanged"],
							acceptance_criteria: ["Protocol files render successfully"],
						},
					};
				}
				if (action.exec_key === "review") {
					return {
						output: "Protocol looks coherent and ready for implementation.",
						structured_output: null,
					};
				}
				throw new Error(`unexpected llm step ${action.exec_key}`);
			},
		},
		async (ctx, ui, pi) => {
			await pi.runCommand("mw", "create-protocol dogfood protocol mode", ctx);
			const active = getActive();
			assert.ok(active, "expected active create-protocol prompt");
			assert.equal(active?.workflowName, "create-protocol");
			assert.equal(active?.mode, "handoff");
			assert.equal(active?.pending.action, "prompt");
			assert.equal(active?.pending.exec_key, "plan-protocol");

			const toolResult = await pi.runTool("workflow_submit", {
				run_id: active?.runId,
				exec_key: active?.pending.exec_key,
				output: "",
				structured_output: {
					name: "Dogfood Protocol Mode",
					context: "Need a small real workflow smoke path for pi development.",
					decision: "Add thin wrapper commands and verify them with integration coverage.",
					rationale: "This gives early dogfood value before release packaging work.",
					consequences_positive: ["Faster iteration on protocol UX"],
					consequences_negative: ["Temporary dev-only bootstrap remains in place"],
					items: [
						{
							type: "step",
							step: {
								name: "Validate wrappers",
								objective: "Confirm create/process wrappers can start real workflows.",
								tasks: [
									{
										heading: "Add smoke coverage",
										description: "Exercise the wrappers with a temp repo.",
										subtasks: [{ title: "Run create-protocol" }],
										acceptance_criteria: ["Protocol files are created"],
									},
								],
								constraints: ["Do not modify shared workflow definitions"],
								impl_notes: "Keep the wrapper layer thin.",
								verification: ["npm run test:integration"],
								context_inline: "Dogfood-first rollout.",
								context_files: ["memento-pi/memory/pi-rollout-plan.md"],
								starting_points: ["memento-pi/src/index.ts"],
								memory_bank_impact: ["memento-pi/memory/pi-rollout-checklist.md"],
								estimate: "30m",
							},
						},
					],
				},
			}, ctx);
			assert.notEqual(toolResult.isError, true, JSON.stringify(toolResult));
			assert.equal(getActive(), null);

			const protocolRoot = join(tmpCwd, ".protocols");
			const dirs = readdirSync(protocolRoot);
			assert.deepEqual(dirs, ["0001-dogfood-protocol-mode"]);
			const protocolDir = join(protocolRoot, dirs[0]!);
			assert.ok(existsSync(join(protocolDir, "prd.md")));
			assert.ok(existsSync(join(protocolDir, "plan.json")));
			assert.ok(existsSync(join(protocolDir, "plan.md")));
			const renderedSteps = readdirSync(protocolDir).filter((name) => name.endsWith(".md") && name !== "prd.md" && name !== "plan.md");
			assert.equal(renderedSteps.length, 1);
			assert.ok(ui.notifications.some((n) => n.message.includes("completed")));
		},
	);
});

test("/mw process-protocol runs real workflow in temp git repo when protocol has no pending steps", async () => {
	const tmpCwd = mkdtempSync(join(tmpdir(), "memento-pi-process-"));
	copyWorkflow(tmpCwd, "process-protocol");
	copyWorkflow(tmpCwd, "develop");

	mkdirSync(join(tmpCwd, ".protocols", "0001-empty-protocol"), { recursive: true });
	writeFileSync(
		join(tmpCwd, ".protocols", "0001-empty-protocol", "plan.md"),
		"# Empty Protocol\n\nNo step files yet.\n",
		"utf-8",
	);

	const { execFileSync } = await import("node:child_process");
	execFileSync("git", ["init"], { cwd: tmpCwd, stdio: "ignore" });
	execFileSync("git", ["config", "user.email", "pi@example.com"], { cwd: tmpCwd, stdio: "ignore" });
	execFileSync("git", ["config", "user.name", "Pi Test"], { cwd: tmpCwd, stdio: "ignore" });
	execFileSync("git", ["add", "."], { cwd: tmpCwd, stdio: "ignore" });
	execFileSync("git", ["commit", "-m", "init"], { cwd: tmpCwd, stdio: "ignore" });

	await withExtension(
		tmpCwd,
		{
			async runRelaySession() {
				throw new Error("relay session should not be used when no protocol steps exist");
			},
			async runLLMStep() {
				throw new Error("llm step should not be used when no protocol steps exist");
			},
		},
		async (ctx, ui, pi) => {
			await pi.runCommand("mw", "process-protocol 1", ctx);
			assert.equal(getActive(), null);
			const protocolDir = join(tmpCwd, ".protocols", "0001-empty-protocol");
			const lastRun = readFileSync(join(protocolDir, ".last_run"), "utf-8").trim();
			assert.match(lastRun, /^[a-f0-9]{12}$/);
			assert.ok(existsSync(join(tmpCwd, ".worktrees", "protocol-0001")));
			const plan = readFileSync(join(protocolDir, "plan.md"), "utf-8");
			assert.match(plan, /status: In Progress/);
			assert.ok(ui.notifications.some((n) => n.message.includes("completed")));
		},
	);
});
