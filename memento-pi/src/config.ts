import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";

export type MementoThinkingLevel = "off" | "minimal" | "low" | "medium" | "high" | "xhigh";

export interface MementoServerConfig {
	command?: string;
	args?: string[];
	cwd?: string;
	env?: Record<string, string>;
}

export interface MementoModelSettings {
	model: string;
	thinkingLevel?: MementoThinkingLevel;
}

export type MementoModelConfig = string | MementoModelSettings;

export interface MementoConfig {
	defaultModel: string;
	defaultProvider: string;
	defaultThinkingLevel?: MementoThinkingLevel;
	models: Record<string, MementoModelConfig>;
	server: MementoServerConfig;
	workflowDirs: string[];
}

export interface ResolvedMementoModel {
	spec: string;
	thinkingLevel?: MementoThinkingLevel;
}

const BUILTIN_DEFAULTS: MementoConfig = {
	defaultModel: "",
	defaultProvider: "",
	defaultThinkingLevel: undefined,
	models: {},
	server: {},
	workflowDirs: [],
};

let cached: { cwd: string; config: MementoConfig } | null = null;

export function getConfig(cwd: string = process.cwd()): MementoConfig {
	const resolvedCwd = resolve(cwd);
	if (cached?.cwd === resolvedCwd) return cached.config;

	const merged: MementoConfig = {
		defaultModel: BUILTIN_DEFAULTS.defaultModel,
		defaultProvider: BUILTIN_DEFAULTS.defaultProvider,
		defaultThinkingLevel: BUILTIN_DEFAULTS.defaultThinkingLevel,
		models: { ...BUILTIN_DEFAULTS.models },
		server: {},
		workflowDirs: [],
	};

	if (process.env.MEMENTO_DEFAULT_MODEL) merged.defaultModel = process.env.MEMENTO_DEFAULT_MODEL;
	if (process.env.MEMENTO_DEFAULT_PROVIDER) merged.defaultProvider = process.env.MEMENTO_DEFAULT_PROVIDER;
	if (isThinkingLevel(process.env.MEMENTO_DEFAULT_THINKING_LEVEL)) {
		merged.defaultThinkingLevel = process.env.MEMENTO_DEFAULT_THINKING_LEVEL;
	}
	for (const [key, value] of Object.entries(process.env)) {
		const m = key.match(/^MEMENTO_MODEL_(.+)$/);
		if (m && value) merged.models[m[1].toLowerCase()] = value;
	}

	applyLegacyFile(join(homedir(), ".pi", "memento-pi.json"), merged);
	applySettingsFile(join(homedir(), ".pi", "agent", "settings.json"), join(homedir(), ".pi", "agent"), merged);
	applyLegacyFile(join(resolvedCwd, ".pi", "memento-pi.json"), merged);
	applySettingsFile(join(resolvedCwd, ".pi", "settings.json"), join(resolvedCwd, ".pi"), merged);

	cached = { cwd: resolvedCwd, config: merged };
	return merged;
}

export function resolveModelSelection(
	blockModel: string | null | undefined,
	cwd: string = process.cwd(),
): ResolvedMementoModel {
	const cfg = getConfig(cwd);
	if (!blockModel) {
		return { spec: cfg.defaultModel, thinkingLevel: cfg.defaultThinkingLevel };
	}
	const alias = cfg.models[blockModel.toLowerCase()];
	if (!alias) {
		return { spec: blockModel, thinkingLevel: cfg.defaultThinkingLevel };
	}
	if (typeof alias === "string") {
		return { spec: alias, thinkingLevel: cfg.defaultThinkingLevel };
	}
	return {
		spec: alias.model,
		thinkingLevel: alias.thinkingLevel ?? cfg.defaultThinkingLevel,
	};
}

export function resetConfigCache(): void {
	cached = null;
}

function applyLegacyFile(path: string, target: MementoConfig): void {
	const parsed = parseJsonFile(path);
	if (!parsed || typeof parsed !== "object") return;
	applyMementoConfig(parsed as Record<string, unknown>, target, resolve(path, ".."));
}

function applySettingsFile(path: string, baseDir: string, target: MementoConfig): void {
	const parsed = parseJsonFile(path);
	if (!parsed || typeof parsed !== "object") return;
	const memento = (parsed as Record<string, unknown>).memento;
	if (!memento || typeof memento !== "object") return;
	applyMementoConfig(memento as Record<string, unknown>, target, baseDir);
}

function parseJsonFile(path: string): unknown {
	let raw: string;
	try {
		raw = readFileSync(path, "utf-8");
	} catch {
		return null;
	}
	try {
		return JSON.parse(raw);
	} catch (err) {
		process.stderr.write(`[memento-pi] invalid config at ${path}: ${(err as Error).message}\n`);
		return null;
	}
}

function applyMementoConfig(parsed: Record<string, unknown>, target: MementoConfig, baseDir: string): void {
	if (typeof parsed.defaultModel === "string") target.defaultModel = parsed.defaultModel;
	if (typeof parsed.defaultProvider === "string") target.defaultProvider = parsed.defaultProvider;
	if (isThinkingLevel(parsed.defaultThinkingLevel)) target.defaultThinkingLevel = parsed.defaultThinkingLevel;
	if (parsed.models && typeof parsed.models === "object") {
		for (const [alias, spec] of Object.entries(parsed.models as Record<string, unknown>)) {
			const normalized = normalizeModelConfig(spec);
			if (normalized) target.models[alias.toLowerCase()] = normalized;
		}
	}
	if (Array.isArray(parsed.workflowDirs)) {
		target.workflowDirs = parsed.workflowDirs
			.filter((value): value is string => typeof value === "string" && value.length > 0)
			.map((value) => resolve(baseDir, value));
	}
	if (parsed.server && typeof parsed.server === "object") {
		const server = parsed.server as Record<string, unknown>;
		if (typeof server.command === "string") target.server.command = server.command;
		if (Array.isArray(server.args)) {
			target.server.args = server.args.filter((value): value is string => typeof value === "string");
		}
		if (typeof server.cwd === "string") target.server.cwd = resolve(baseDir, server.cwd);
		if (server.env && typeof server.env === "object") {
			const env: Record<string, string> = {};
			for (const [key, value] of Object.entries(server.env as Record<string, unknown>)) {
				if (typeof value === "string") env[key] = value;
			}
			target.server.env = env;
		}
	}
}

function normalizeModelConfig(value: unknown): MementoModelConfig | null {
	if (typeof value === "string") return value;
	if (!value || typeof value !== "object") return null;
	const record = value as Record<string, unknown>;
	if (typeof record.model !== "string") return null;
	const normalized: MementoModelSettings = { model: record.model };
	if (isThinkingLevel(record.thinkingLevel)) normalized.thinkingLevel = record.thinkingLevel;
	return normalized;
}

function isThinkingLevel(value: unknown): value is MementoThinkingLevel {
	return (
		value === "off" ||
		value === "minimal" ||
		value === "low" ||
		value === "medium" ||
		value === "high" ||
		value === "xhigh"
	);
}
