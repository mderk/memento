import { readFileSync } from "node:fs";
import type { PromptAction, SubagentAction } from "./types.ts";

export function renderPendingPrompt(
	run: { workflowName: string; runId: string; stepCount: number },
	a: PromptAction | SubagentAction,
): string {
	const parts: string[] = [];
	parts.push(`<workflow-pending>`);
	parts.push(`workflow: ${run.workflowName}`);
	parts.push(`run_id: ${run.runId}`);
	parts.push(`step: ${run.stepCount}`);
	parts.push(`exec_key: ${a.exec_key}`);
	if (a.model) parts.push(`model: ${a.model}`);
	if (a.tools?.length) parts.push(`allowed_tools: ${a.tools.join(", ")}`);

	const hasSchema = a.action === "prompt" && Boolean(a.output_schema_name || a.schema_file || a.json_schema);

	if (a.action === "prompt" && a.output_schema_name) parts.push(`output_schema: ${a.output_schema_name}`);
	if (a.action === "prompt" && a.schema_file) parts.push(`schema_file: ${a.schema_file}`);
	if (a.action === "prompt" && a.result_dir) parts.push(`result_dir: ${a.result_dir}`);
	if (a.action === "subagent") parts.push(`handoff_source: leaf-subagent`);

	let promptText = a.prompt;
	if (a.action === "prompt" && a.prompt_file && !promptText) {
		try {
			promptText = readFileSync(a.prompt_file, "utf-8");
		} catch {
			promptText = `(failed to read ${a.prompt_file})`;
		}
	}

	if (a.action === "prompt" && a.context_files?.length) {
		parts.push(`context_files:`);
		for (const f of a.context_files) parts.push(`  - ${f}`);
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
			`For large results (> ~2KB), write them to "${a.action === "prompt" ? (a.result_dir ?? "result_dir") : "result_dir"}/output.json" and pass only {"output_file": "<that path>"} instead of inlining. ` +
			`Do not call workflow_submit more than once for the same exec_key.`,
	);
	parts.push(`</workflow-pending>`);
	return parts.join("\n");
}
