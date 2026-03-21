# Edit Protocol Plan

Modify an existing protocol plan based on user instructions.

## Current Plan

The current plan JSON is stored in `{{variables.protocol_dir}}/plan.json`. Read it to understand the existing structure.

## User Instructions

{{variables.edit_instructions}}

## Guidelines

1. Read the current plan.json from the protocol directory
2. Apply the user's requested changes
3. Preserve all existing content that isn't explicitly changed
4. Maintain the same JSON structure (ProtocolPlan schema)
5. Update estimates if the scope changed significantly

## Output

Respond with a JSON object matching the ProtocolPlan schema — the complete updated plan.
