# Ask User — Parallel Check

This step runs in parallel for each item. The current item is "{{variables.item}}".

## Rules

If the item is "beta": you MUST call the ask_user tool. Ask exactly:
- Message: "Approve item beta?"
- Options: ["yes", "skip"]
Then respond with: "item=beta,approved=<ANSWER>"

If the item is NOT "beta": do NOT call ask_user. Just respond with:
"item={{variables.item}},approved=auto"

Only "beta" requires user approval. All other items are auto-approved.
