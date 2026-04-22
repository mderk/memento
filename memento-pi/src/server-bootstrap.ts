import { homedir } from "node:os";
import { join } from "node:path";

export interface ServerConfig {
	cwd: string;
	command: string;
	args: string[];
}

export function resolveServerConfig(): ServerConfig {
	const cwd = process.env.MEMENTO_WORKFLOW_DIR ?? join(homedir(), "Documents/projects/memento/memento-workflow");
	return {
		cwd,
		command: "uv",
		args: ["run", "python", "-m", "scripts.server"],
	};
}
