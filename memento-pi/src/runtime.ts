import type { ExtensionAPI, ExtensionContext } from "@mariozechner/pi-coding-agent";
import { MementoClient } from "./client.ts";
import { runLLMStep, type LLMStepResult } from "./llm-step.ts";
import { runRelaySession, type RelayResult } from "./relay-session.ts";
import { resolveServerConfig, type ServerConfig } from "./server-bootstrap.ts";
import type { SubagentAction } from "./types.ts";

export interface ClientLike {
	call(method: string, params?: Record<string, unknown>): Promise<any>;
	shutdown(): Promise<void>;
}

export interface RuntimeDeps {
	resolveServerConfig(): ServerConfig;
	createClient(config: ServerConfig): ClientLike;
	runLLMStep(
		action: SubagentAction,
		pi: ExtensionAPI,
		ctx: ExtensionContext,
		signal?: AbortSignal,
	): Promise<LLMStepResult>;
	runRelaySession(
		action: SubagentAction,
		pi: ExtensionAPI,
		ctx: ExtensionContext,
		client: ClientLike,
		signal?: AbortSignal,
	): Promise<RelayResult>;
}

export const defaultRuntimeDeps: RuntimeDeps = {
	resolveServerConfig,
	createClient: (config) => new MementoClient(config),
	runLLMStep,
	runRelaySession,
};
