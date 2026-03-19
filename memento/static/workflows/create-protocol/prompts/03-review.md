# Review Generated Protocol

The protocol has been generated. Review the output and present a summary to the user.

## Render Result

{{variables.render_result}}

## Instructions

1. Read the generated `plan.md`:

   `{{variables.protocol_dir}}/plan.md`

2. Spot-check 1-2 step files to verify they look correct (proper markers, reasonable tasks)

3. Present to the user:
   - Protocol name and step count
   - The directory structure (which groups and steps were created)
   - The ADR summary (decision + key trade-offs)
   - Total estimated time
   - Any concerns or suggestions

4. Remind the user:
   - Review the generated files before executing
   - Run `/process-protocol` when ready to start implementation
   - They can edit step files manually to adjust tasks, constraints, or verification commands

Do NOT start execution. The user decides when to proceed.
