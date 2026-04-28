import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { getActive, setActive } from "../src/state.ts";
import { createMementoExtension } from "../src/index.ts";
import { loadScenario } from "./helpers/scenario.ts";
import { FakePi, FakeUI, createFakeContext, runScenarioThroughExtension } from "./helpers/harness.ts";

test("thorough test-workflow completes through extension with relay resume", async () => {
	const scenario = loadScenario("thorough-relay-resume.json");
	const run = await runScenarioThroughExtension(scenario);

	assert.deepEqual(run.restartEvents, [{ scope: "relay-child", exec_key: "session-analyze" }]);
	assert.deepEqual(run.handoffExecKeys, [
		"llm-classify",
		"llm-summarize",
		"llm-ask-single",
	]);
	assert.equal(run.pi.messages[0]?.text, "Continue the active workflow.");
	assert.ok(run.ui.selectCalls.length >= 1);
	assert.ok(run.ui.confirmCalls.length >= 1);
	assert.ok(run.ui.notifications.some((n) => n.message.includes("completed")));
	assert.equal(getActive(), null);
});

test("before_agent_start injects only for handoff prompt", async () => {
	setActive(null);
	const pi = new FakePi();
	const ui = new FakeUI(loadScenario("quick-accept-yes.json"));
	const ctx = createFakeContext(process.cwd(), ui);
	createMementoExtension({
		resolveServerConfig: () => ({ cwd: process.cwd(), command: "true", args: [] }),
		createClient: () => ({
			async call() { throw new Error("not used"); },
			async shutdown() {},
		}),
		async runLLMStep() { throw new Error("not used"); },
		async runRelaySession() { throw new Error("not used"); },
	})(pi as any);

	let injected = await pi.trigger("before_agent_start", { systemPrompt: "BASE" }, ctx);
	assert.equal(injected, undefined);

	setActive({
		runId: "r1",
		workflowName: "wf",
		mode: "awaiting-user",
		pending: {
			action: "ask_user",
			run_id: "r1",
			exec_key: "mode",
			prompt_type: "choice",
			message: "Choose",
			options: ["a", "b"],
		},
		stepCount: 1,
	});
	injected = await pi.trigger("before_agent_start", { systemPrompt: "BASE" }, ctx);
	assert.equal(injected, undefined);

	setActive({
		runId: "r1",
		workflowName: "wf",
		mode: "auto-running",
		pending: {
			action: "subagent",
			run_id: "r1",
			exec_key: "relay",
			prompt: "p",
			relay: true,
			child_run_id: "r1>c1",
		},
		stepCount: 2,
	});
	injected = await pi.trigger("before_agent_start", { systemPrompt: "BASE" }, ctx);
	assert.equal(injected, undefined);

	setActive({
		runId: "r1",
		workflowName: "wf",
		mode: "handoff",
		pending: {
			action: "prompt",
			run_id: "r1",
			exec_key: "llm-step",
			prompt: "hello",
		},
		stepCount: 3,
	});
	injected = await pi.trigger("before_agent_start", { systemPrompt: "BASE" }, ctx);
	assert.ok(injected?.systemPrompt?.includes("<workflow-pending>"));
	assert.ok(injected.systemPrompt.includes("exec_key: llm-step"));

	setActive(null);
});

test("quick test-workflow accept/no branch can run end-to-end through extension", async () => {
	const scenario = loadScenario("quick-accept-no.json");
	const run = await runScenarioThroughExtension(scenario);
	const stateRoot = join(run.tmpCwd, ".workflow-state");
	assert.ok(existsSync(stateRoot));
	const runDir = readFileSync(join(stateRoot, await (async () => {
		const { readdirSync } = await import("node:fs");
		return readdirSync(stateRoot)[0]!;
	})(), "state.json"), "utf-8");
	assert.ok(runDir.includes("confirm-results"));
	assert.equal(getActive(), null);
});
