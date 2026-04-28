import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

export interface ScenarioStep {
	match: string;
	submit: Record<string, unknown>;
	interactions?: Array<{ ui: "choice" | "confirm" | "input"; answer: string }>;
}

export interface RestartPoint {
	scope: string;
	afterExecKey: string;
}

export interface Scenario {
	name: string;
	workflow: string;
	workflowDirs: string[];
	variables?: Record<string, unknown>;
	steps: ScenarioStep[];
	restarts?: RestartPoint[];
	expect?: Record<string, unknown>;
}

const HERE = dirname(fileURLToPath(import.meta.url));
const FIXTURE_DIR = resolve(HERE, "../../../memento-workflow/tests/fixtures/test-workflow");

export function loadScenario(name: string): Scenario {
	return JSON.parse(readFileSync(resolve(FIXTURE_DIR, name), "utf-8")) as Scenario;
}

export function resolveWorkflowDirs(scenario: Scenario): string[] {
	return scenario.workflowDirs.map((p) => resolve(HERE, "../../../memento-workflow", p));
}

export function matchScenarioStep(scenario: Scenario, execKey: string): ScenarioStep {
	for (const step of scenario.steps) {
		const regex = new RegExp(`^${escapeRegex(step.match).replace(/\\\*/g, ".*")}$`);
		if (regex.test(execKey)) return step;
	}
	throw new Error(`No canned scenario step for exec_key '${execKey}' in scenario '${scenario.name}'`);
}

function escapeRegex(s: string): string {
	return s.replace(/[|\\{}()[\]^$+?.*]/g, "\\$&");
}
