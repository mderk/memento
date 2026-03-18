# Rule: Generating a Product Requirements Document

## Goal

Guide AI assistants in creating a clear, actionable PRD in Markdown format from user input, focusing on WHAT to build and WHY (not HOW).

## Output

- **Format**: Markdown (`.md`)
- **Location**: `.protocols/NNNN-feature-name/`
- **Filename**: `prd.md`
- **Sections**: 9 required sections (Introduction through Open Questions)
- **Audience**: Junior developer (clear, explicit requirements)

## Process

1. **Receive Feature Request**: User provides brief description
2. **Create Protocol Directory**: Determine next number (`ls .protocols/`, take max + 1, default 0001). Create `.protocols/NNNN-feature-name/`
3. **Explore** (silent): Investigate codebase and brainstorm possibilities
4. **Propose Alternatives**: Present 2-3 approaches with trade-offs, ask user to pick using `AskUserQuestion`
5. **Clarify**: Ask 2-4 targeted questions one at a time, each via `AskUserQuestion`
6. **Generate PRD**: Create PRD with 9 sections (see Output Format below)
7. **Save PRD**: Write to `.protocols/NNNN-feature-name/prd.md`
8. **Report**: Tell user the protocol directory path and suggest next steps: `/create-spec NNNN` (optional) or `/create-protocol NNNN`

Even simple features benefit from this process — unexamined assumptions cause the most wasted work.

## Explore Phase (silent — no output)

The user's description is likely vague. Before saying anything, do two things:

**Scan the codebase** — find relevant code, models, patterns, and constraints.

**Think creatively** — brainstorm how this feature could work:
- What are 2-3 meaningfully different approaches?
- What scope variations exist (lean MVP vs full-featured)?
- What UX patterns does the codebase already use that could apply?
- What are the real trade-offs between approaches (not just "pros and cons" but actual consequences: development cost, user experience, future flexibility)?

The goal: arrive at the next phase with concrete alternatives to present, not questions to ask.

## Propose Alternatives

**IMPORTANT**: Use the `AskUserQuestion` tool for this step. Do NOT just print options as text.

First, output a brief summary of what you found and your 2-3 approaches (each with a coherent user experience vision and honest trade-offs). Then immediately call `AskUserQuestion` with the options.

Each alternative should be:
- A **coherent vision**, not just a technical option — describe what the user experience looks like
- Grounded in **what you found in the codebase** — reference existing patterns, models, infrastructure
- Honest about **trade-offs** — what you gain, what you give up, what gets harder later

This is the most important step — it turns a vague idea into a concrete shape.

**Example** (user said "add notifications"):

Output text:
> I looked at the codebase. You have WebSocket in `realtime/ws.py` and email via `services/email.py` (used for password resets). Here are three ways notifications could work:

Then call `AskUserQuestion` with question "Which direction?" and options:
- "A) Lightweight toasts — flash via existing WebSocket, no persistence. Simple but users miss offline notifications"
- "B) Notification center — new model, bell icon, unread count, history. More work but users catch up on missed items"
- "C) Hybrid — real-time toasts + daily email digest. Leverages both systems, needs seen-state tracking"

## Clarify Phase

After the user picks a direction, ask **2-4 follow-up questions one at a time**. Each question **must** use the `AskUserQuestion` tool with prepared options — do NOT output questions as text.

Each question should:
- Be specific to the **chosen approach** (not generic)
- Offer **concrete options you came up with** — not blank fields to fill

These questions resolve remaining ambiguities — scope boundaries, edge cases, priority of sub-features.

Skip anything the user already answered. After all answers, proceed to Generate PRD.

## Output Format

The generated PRD _must_ include these 9 sections:

1. **Introduction**: Feature description and problem it solves
2. **Goals**: Specific, measurable objectives
3. **User Stories**: "As a [user], I want [action] so that [benefit]"
4. **Functional Requirements**: Numbered list of what system must do
5. **Non-Goals**: Explicitly what feature will NOT include
6. **Design Considerations** (optional): UI/UX requirements, mockups
7. **Technical Considerations** (optional): Known constraints, dependencies
8. **Success Metrics**: How success is measured
9. **Open Questions**: Remaining questions to resolve

**Important**: Use generic terms, not hardcoded technology:

- "passwords must be hashed securely" (not "use bcrypt")
- "session tokens with appropriate expiration" (not "use JWT")

## Related Documentation

- [Create Spec Workflow](./create-spec.md)
- [Create Protocol Workflow](./create-protocol.md)
- `/develop` workflow
