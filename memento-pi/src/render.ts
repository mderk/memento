import { readFileSync } from "node:fs";
import type { PendingAction } from "./state.ts";
import type { PromptAction, SubagentAction } from "./types.ts";

export function renderPending(
	run: { workflowName: string; runId: string; stepCount: number },
	a: PendingAction,
): string {
	const parts: string[] = [];
	parts.push(`<workflow-pending>`);
	parts.push(`workflow: ${run.workflowName}`);
	parts.push(`run_id: ${run.runId}`);
	parts.push(`step: ${run.stepCount}`);
	parts.push(`exec_key: ${a.exec_key}`);
	if (a.action === "subagent") parts.push(`isolation: subagent (isolated reasoning pass)`);
	if (a.model) parts.push(`model: ${a.model}`);
	if (a.tools?.length) parts.push(`allowed_tools: ${a.tools.join(", ")}`);

	const asPrompt = a as PromptAction;
	const asSubagent = a as SubagentAction;
	const hasSchema = a.action === "prompt" && !!(asPrompt.output_schema_name || asPrompt.schema_file || asPrompt.json_schema);

	if (asPrompt.output_schema_name) parts.push(`output_schema: ${asPrompt.output_schema_name}`);
	if (asPrompt.schema_file) parts.push(`schema_file: ${asPrompt.schema_file}`);
	if (asSubagent.context_hint) parts.push(`context_hint: ${asSubagent.context_hint}`);
	if (asPrompt.result_dir) parts.push(`result_dir: ${asPrompt.result_dir}`);

	let promptText = a.action === "prompt" ? asPrompt.prompt : asSubagent.prompt;
	if (a.action === "prompt" && asPrompt.prompt_file) {
		try {
			promptText = readFileSync(asPrompt.prompt_file, "utf-8");
		} catch {
			promptText = `(failed to read ${asPrompt.prompt_file})`;
		}
	}

	if (a.action === "prompt" && asPrompt.context_files?.length) {
		parts.push(`context_files:`);
		for (const f of asPrompt.context_files) parts.push(`  - ${f}`);
	}

	parts.push(``);
	parts.push(`--- prompt ---`);
	parts.push(promptText);
	parts.push(`--- end prompt ---`);
	parts.push(``);

	const outputRule = hasSchema
		? `Put the result ONLY in "structured_output" (must match the schema). Leave "output" empty, or use it for a ONE-LINE human summary (e.g. "classified: backend/feature/simple"). Do NOT duplicate the JSON into "output".`
		: `Put the result in "output". Leave "structured_output" unset.`;

	parts.push(
		`When done, call workflow_submit with exec_key="${a.exec_key}" and run_id="${run.runId}". ` +
			`${outputRule} ` +
			`For large results (> ~2KB), write them to "${asPrompt.result_dir ?? "result_dir"}/output.json" and pass only {"output_file": "<that path>"} instead of inlining. ` +
			`Do not call workflow_submit more than once for the same exec_key.`,
	);
	parts.push(`</workflow-pending>`);
	return parts.join("\n");
}
