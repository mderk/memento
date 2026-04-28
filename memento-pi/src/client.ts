import { type ChildProcessWithoutNullStreams, spawn } from "node:child_process";
import { createInterface, type Interface } from "node:readline";
import type { ClientLike } from "./runtime.ts";
import type { ServerConfig } from "./server-bootstrap.ts";

interface Pending {
	resolve: (value: unknown) => void;
	reject: (err: Error) => void;
}

export class MementoClient implements ClientLike {
	private proc: ChildProcessWithoutNullStreams;
	private rl: Interface;
	private pending = new Map<string, Pending>();
	private nextId = 1;
	private closed = false;

	constructor(config: ServerConfig) {
		this.proc = spawn(config.command, config.args, {
			cwd: config.cwd,
			env: { ...process.env, ...(config.env ?? {}) },
			stdio: ["pipe", "pipe", "pipe"],
		});
		this.proc.on("exit", (code) => {
			this.closed = true;
			const err = new Error(`memento server exited (code=${code})`);
			for (const p of this.pending.values()) p.reject(err);
			this.pending.clear();
		});
		const showBackendStderr = process.env.MEMENTO_PI_DEBUG === "1"
			|| config.env?.WORKFLOW_DEBUG === "1"
			|| process.env.WORKFLOW_DEBUG === "1";
		if (showBackendStderr) {
			this.proc.stderr.on("data", (chunk) => {
				process.stderr.write(`[memento-pi] ${chunk}`);
			});
		}
		this.rl = createInterface({ input: this.proc.stdout });
		this.rl.on("line", (line) => this.handleLine(line));
	}

	private handleLine(line: string): void {
		if (!line.trim()) return;
		let msg: { id?: string; result?: unknown; error?: { message: string; type?: string } };
		try {
			msg = JSON.parse(line);
		} catch {
			process.stderr.write(`[memento-pi] bad line: ${line}\n`);
			return;
		}
		const id = msg.id;
		if (id == null) return;
		const pending = this.pending.get(id);
		if (!pending) return;
		this.pending.delete(id);
		if (msg.error) pending.reject(new Error(msg.error.message));
		else pending.resolve(msg.result);
	}

	async call(method: string, params: Record<string, unknown> = {}): Promise<any> {
		if (this.closed) throw new Error("memento server already exited");
		const id = String(this.nextId++);
		return new Promise((resolve, reject) => {
			this.pending.set(id, { resolve, reject });
			this.proc.stdin.write(`${JSON.stringify({ id, method, params })}\n`, (err) => {
				if (err) {
					this.pending.delete(id);
					reject(err);
				}
			});
		});
	}

	async shutdown(): Promise<void> {
		if (this.closed) return;
		this.proc.stdin.end();
		await new Promise<void>((resolve) => {
			const timer = setTimeout(() => {
				this.proc.kill("SIGTERM");
				resolve();
			}, 2000);
			this.proc.once("exit", () => {
				clearTimeout(timer);
				resolve();
			});
		});
	}
}
