# Summarize Workflow State

Summarize the current workflow state as structured JSON.

Items detected: {{results.detect.structured_output.count}}
Mode chosen: {{results.mode.output}}

Return a JSON object with:
- total_items: number of items detected
- status: "complete"
- notes: a brief summary of the workflow run
