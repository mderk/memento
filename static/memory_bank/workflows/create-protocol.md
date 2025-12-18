# Rule: Creating a Protocol from a PRD

## Goal

To guide an AI assistant in creating a protocol structure based on an existing Product Requirements Document (PRD). A protocol is a structured approach to implementing features, organized into numbered steps with detailed task breakdowns and documented rationale using mini-ADR format.

## Protocol Structure

A protocol consists of:

- **Protocol folder**: `.protocols/XXXX-{protocol-name}/` where XXXX is a 4-digit protocol number
- **plan.md**: High-level plan in mini-ADR format (Architecture Decision Record) documenting Context, Decision, Rationale, and Consequences
- **Step files**: `YY-{step-name}.md` for detailed step-by-step implementation tasks

## Output

- **Format:** Directory with Markdown files
- **Location:** `.protocols/XXXX-{protocol-name}/`
- **Files:**
  - `plan.md` - High-level overview with mini-ADR header
  - `01-{step-name}.md` - First implementation step
  - `02-{step-name}.md` - Second implementation step
  - etc.

## Process

1. **Receive PRD Reference:** The user points the AI to a specific PRD file and optionally provides a protocol number (XXXX).

2. **Determine Protocol Number:**

   - If protocol number provided: use that number
   - If no protocol number: scan `.protocols/` directory to find highest existing number and increment by 1
   - If `.protocols/` doesn't exist or is empty: start with 0001
   - Inform user: "Creating protocol XXXX: {protocol-name}"

   **How to scan `.protocols/` directory:**
   - Use `ls -d .protocols/*/` or glob pattern `.protocols/*/` to find **subdirectories** (not files)
   - Look for directories matching pattern `XXXX-*` (4 digits followed by hyphen)
   - Ignore system files like `.DS_Store` - these are NOT protocols
   - Extract the 4-digit prefix from each directory name and find the maximum
   - Example: if directories are `0001-auth/`, `0005-dashboard/`, next protocol is `0006`

3. **Analyze PRD:** Read and analyze the functional requirements, user stories, technical constraints, and success criteria.

4. **Phase 1: Generate Protocol Plan (plan.md)**

   - Create the protocol directory: `.protocols/XXXX-{protocol-name}/`
   - Generate `plan.md` with:
     - **Mini-ADR Header**: Context, Decision, Rationale, Consequences
     - **High-level Steps**: List of major implementation phases (typically 3-7 steps)
   - Present to user: "I have generated the protocol plan with X high-level steps. Ready to generate detailed step files? Respond with 'Go' to proceed."
   - If user is not satisfied, revise based on feedback
   - If user instructed to make full protocol, skip confirmation step

5. **Wait for Confirmation:** Pause and wait for user to respond with "Go".

6. **Phase 2: Generate Step Files**

   - For each step in the plan, create a separate file: `YY-{step-name}.md`
   - Each step file contains:
     - **Step Overview**: What this step accomplishes
     - **Tasks**: Detailed actionable tasks (5-7 per step)
     - **Methodology Notes**: How to approach the tasks
     - **Relevant Files**: Files to create/modify
     - **Testing Strategy**: How to verify completion

7. **Generate Protocol Structure:** Create all files in the protocol directory.

8. **Summary Output:** Provide a summary showing:
   - Protocol number and name
   - Number of steps created
   - Brief description of each step
   - Next actions for the developer

## plan.md Format

```markdown
# Protocol XXXX: {Protocol Name}

## Context

What is the current situation? What problem are we solving? What are the constraints?

## Decision

What approach are we taking? What is the high-level architecture/implementation strategy?

## Rationale

WHY are we doing it this way? What alternatives were considered? What are the trade-offs?

## Consequences

What are the positive outcomes? What are the potential challenges? What technical debt might we incur?

---

## Implementation Steps

- [ ] Step 1: {Step Name} - Brief description
- [ ] Step 2: {Step Name} - Brief description
- [ ] Step 3: {Step Name} - Brief description

---

## Success Criteria

- [ ] Criterion 1
- [ ] Criterion 2
```

## Step File Format (YY-{step-name}.md)

```markdown
# Step YY: {Step Name}

## Overview

Brief description of what this step accomplishes and how it fits into the overall protocol.

## Tasks

- [ ] YY.1 Task description

  - Implementation details
  - Key considerations

- [ ] YY.2 Task description
  - Implementation details

## Methodology

How to approach these tasks:

1. Start by...
2. Then proceed to...

## Relevant Files

- `path/to/file.ts` - Description and purpose

## Testing Strategy

- Unit tests: What to test and how
- Integration tests: If applicable

## Completion Criteria

- [ ] All tasks completed
- [ ] Tests passing
- [ ] Code reviewed
```

## Interaction Model

The process requires a pause after generating the protocol plan to get user confirmation ("Go") before proceeding to generate detailed step files. This ensures the high-level approach aligns with user expectations.

## Naming Conventions

- **Protocol numbers**: 4 digits, zero-padded (0001, 0040, 0137)
- **Protocol folder**: `.protocols/XXXX-feature-name/` (use kebab-case)
- **Step files**: `01-step-name.md`, `02-step-name.md` (use kebab-case)

## Target Audience

Assume the primary reader is a **mid-level developer** who needs clear guidance on implementation but can handle technical complexity.
