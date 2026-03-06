# Ask User — Parallel Check

This step runs in parallel for each item. The current item is "{{variables.item}}".

## Rules

If the item is "conditional": you MUST call the ask_user tool. Ask exactly:
- Message: "Conditional logic requires manual review. Approve?"
- Options: ["yes", "skip"]
Then respond with: "item=conditional,approved=<ANSWER>"

If the item is NOT "conditional": do NOT call ask_user. Just respond with:
"item={{variables.item}},approved=auto"

Only "conditional" requires user approval. All other items are auto-approved.
