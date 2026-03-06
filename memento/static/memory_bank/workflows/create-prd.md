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
3. **Ask Clarifying Questions**: Resolve ambiguities — problem being solved, target user, desired functionality, acceptance criteria, scope boundaries, data requirements, design needs, edge cases
4. **Generate PRD**: Create PRD with 9 sections (see Output Format below)
5. **Save PRD**: Write to `.protocols/NNNN-feature-name/prd.md`
6. **Report**: Tell user the protocol directory path and suggest next steps: `/create-spec NNNN` (optional) or `/create-protocol NNNN`

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
