import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export interface MementoConfig {
	defaultModel: string;
	defaultProvider: string;
	models: Record<string, string>;
}

const BUILTIN_DEFAULTS: MementoConfig = {
	defaultModel: "claude-agent-sdk/claude-sonnet-4-6",
	defaultProvider: "claude-agent-sdk",
	models: {
		sonnet: "claude-agent-sdk/claude-sonnet-4-6",
		haiku: "claude-agent-sdk/claude-haiku-4-5",
		opus: "claude-agent-sdk/claude-opus-4-7",
	},
};

let cached: MementoConfig | null = null;

export function getConfig(cwd: string = process.cwd()): MementoConfig {
	if (cached) return cached;

	const merged: MementoConfig = {
		defaultModel: BUILTIN_DEFAULTS.defaultModel,
		defaultProvider: BUILTIN_DEFAULTS.defaultProvider,
		models: { ...BUILTIN_DEFAULTS.models },
	};

	// Layer 1: env vars
	if (process.env.MEMENTO_DEFAULT_MODEL) merged.defaultModel = process.env.MEMENTO_DEFAULT_MODEL;
	if (process.env.MEMENTO_DEFAULT_PROVIDER) merged.defaultProvider = process.env.MEMENTO_DEFAULT_PROVIDER;
	for (const [key, value] of Object.entries(process.env)) {
		const m = key.match(/^MEMENTO_MODEL_(.+)$/);
		if (m && value) merged.models[m[1].toLowerCase()] = value;
	}

	// Layer 2: user config ~/.pi/memento-pi.json
	applyFile(join(homedir(), ".pi", "memento-pi.json"), merged);

	// Layer 3: project config <cwd>/.pi/memento-pi.json
	applyFile(join(cwd, ".pi", "memento-pi.json"), merged);

	cached = merged;
	return merged;
}

export function resetConfigCache(): void {
	cached = null;
}

function applyFile(path: string, target: MementoConfig): void {
	let raw: string;
	try {
		raw = readFileSync(path, "utf-8");
	} catch {
		return;
	}
	let parsed: Partial<MementoConfig>;
	try {
		parsed = JSON.parse(raw);
	} catch (err) {
		process.stderr.write(`[memento-pi] invalid config at ${path}: ${(err as Error).message}\n`);
		return;
	}
	if (typeof parsed.defaultModel === "string") target.defaultModel = parsed.defaultModel;
	if (typeof parsed.defaultProvider === "string") target.defaultProvider = parsed.defaultProvider;
	if (parsed.models && typeof parsed.models === "object") {
		for (const [alias, spec] of Object.entries(parsed.models)) {
			if (typeof spec === "string") target.models[alias.toLowerCase()] = spec;
		}
	}
}
