import test from "node:test";
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { getConfig, resetConfigCache, resolveModelSelection } from "../src/config.ts";

test("resolveModelSelection supports object aliases with per-alias thinking levels", () => {
	const tmpCwd = mkdtempSync(join(tmpdir(), "memento-pi-config-"));
	mkdirSync(join(tmpCwd, ".pi"), { recursive: true });
	writeFileSync(
		join(tmpCwd, ".pi", "settings.json"),
		JSON.stringify(
			{
				memento: {
					defaultProvider: "openai-codex",
					defaultModel: "openai-codex/gpt-5.4",
					defaultThinkingLevel: "medium",
					models: {
						sonnet: "openai-codex/gpt-5.4",
						opus: {
							model: "openai-codex/gpt-5.4",
							thinkingLevel: "high",
						},
						haiku: {
							model: "openai-codex/gpt-5.4-mini",
							thinkingLevel: "off",
						},
					},
				},
			},
			null,
			2,
		),
		"utf-8",
	);

	resetConfigCache();
	assert.deepEqual(resolveModelSelection(undefined, tmpCwd), {
		spec: "openai-codex/gpt-5.4",
		thinkingLevel: "medium",
	});
	assert.deepEqual(resolveModelSelection("sonnet", tmpCwd), {
		spec: "openai-codex/gpt-5.4",
		thinkingLevel: "medium",
	});
	assert.deepEqual(resolveModelSelection("opus", tmpCwd), {
		spec: "openai-codex/gpt-5.4",
		thinkingLevel: "high",
	});
	assert.deepEqual(resolveModelSelection("haiku", tmpCwd), {
		spec: "openai-codex/gpt-5.4-mini",
		thinkingLevel: "off",
	});
	assert.equal(getConfig(tmpCwd).models.haiku && typeof getConfig(tmpCwd).models.haiku, "object");

	resetConfigCache();
});
