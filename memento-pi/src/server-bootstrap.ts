import { homedir } from "node:os";
import { join } from "node:path";
import { getConfig } from "./config.ts";

export interface ServerConfig {
	cwd: string;
	command: string;
	args: string[];
	env?: Record<string, string>;
}

export function resolveServerConfig(): ServerConfig {
	const cfg = getConfig();
	return {
		cwd: process.env.MEMENTO_WORKFLOW_DIR ?? cfg.server.cwd ?? join(homedir(), "Documents/projects/memento/memento-workflow"),
		command: cfg.server.command ?? "uv",
		args: cfg.server.args ?? ["run", "python", "-m", "scripts.server"],
		env: cfg.server.env,
	};
}
