# Rule: Processing a Protocol

## Goal

To guide an AI assistant in implementing tasks from a protocol. Can process either a specific step or continue from where left off.

## Input

- Protocol number (XXXX) - **Required**
- Step number (YY) - **Optional** (if not provided, continue from last incomplete step)
- Additional instructions - **Optional** (e.g., "Focus on testing", "Complete tasks 3.1-3.3")

## Process

1. **Locate Protocol:**
   - Navigate to `.protocols/XXXX-*/` (find by protocol number)
   - Verify protocol exists and is properly structured

2. **Read Protocol Context:**
   - Read `plan.md` to understand:
     - Overall context and rationale (mini-ADR)
     - List of all implementation steps
     - Success criteria for the entire protocol

3. **Determine Step to Process:**
   - If step number (YY) provided: use that step
   - If no step number: scan all step files to find first incomplete step
   - Inform user which step will be processed

4. **Read Step File:**
   - Read `YY-{step-name}.md` for the determined step
   - Understand:
     - Step overview and objectives
     - Task list and implementation details
     - Methodology and approach guidelines
     - Relevant files to work with
     - Testing strategy

5. **Read Memory Bank Context:**
   - `.memory_bank/README.md` - Project overview
   - `.memory_bank/tech_stack.md` - Technical architecture
   - Relevant pattern/guide files mentioned in the step

6. **Plan Task Execution:**
   - Present task list to user
   - Confirm which tasks to implement in this session
   - Identify dependencies between tasks
   - Note any blockers or questions

7. **Execute Tasks:**
   - Follow the methodology described in the step file
   - Implement tasks in logical order
   - Use TodoWrite to track progress
   - Mark tasks as completed in the step file as you go
   - Follow coding patterns from Memory Bank
   - Apply quality standards from tech stack guide

8. **Testing:**
   - Implement tests according to testing strategy
   - Run tests after each task or logical group
   - Use @test-runner agent to run tests
   - Fix any issues before proceeding
   - Update step file with test results

9. **Code Review:**
   - If step is complete or significant progress made:
     - Invoke @code-reviewer agent
     - Address feedback
     - Update code accordingly

10. **Update Step File:**
    - Mark completed tasks with `[x]`
    - Add notes about implementation decisions
    - Document any deviations from plan
    - Note blockers or issues for next session

11. **Summary:**
    - Report completed tasks
    - Highlight any issues or blockers
    - Suggest next steps
    - Update completion criteria checklist

## Task Tracking Strategy

Use TodoWrite to maintain a live task list during implementation:

```json
[
  {"content": "Task YY.1: Description", "status": "completed", "activeForm": "Completing Task YY.1"},
  {"content": "Task YY.2: Description", "status": "in_progress", "activeForm": "Implementing Task YY.2"},
  {"content": "Task YY.3: Description", "status": "pending", "activeForm": "Starting Task YY.3"}
]
```

## File Update Strategy

After completing tasks, update the step file to reflect progress:

```markdown
- [x] YY.1 ~~Task description~~
  - ✅ Completed on 2025-11-20
  - Notes: Used alternative approach due to X

- [x] YY.2 ~~Task description~~
  - ✅ Completed on 2025-11-20

- [ ] YY.3 Task description
  - 🚧 In progress
  - Blocker: Waiting for API endpoint implementation
```

## Methodology Notes

Follow the methodology section in the step file carefully. It provides:
- Order of operations
- Key considerations
- Common pitfalls to avoid
- Best practices for this specific step

## Integration with Quality Agents

### Automatic Invocation
After completing a significant portion of a step:
1. **@code-reviewer** - Automatically invoked for code quality
2. **@design-reviewer** - If UI changes were made
3. **@test-runner** - If explicitly requested or step is complete

### Manual Invocation
User can request specific agent reviews at any time.

## Handling Blockers

If you encounter a blocker:
1. Document it clearly in the step file
2. Mark the task as blocked: `- [ ] YY.X Task description ⛔ Blocked: Reason`
3. Suggest alternatives or workarounds
4. Move to next independent task if possible
5. Summarize blockers at end of session

## Completion Criteria

A step is considered complete when:
- [ ] All tasks are marked as completed
- [ ] All tests are passing
- [ ] Code review has been performed and feedback addressed
- [ ] Step file completion criteria are all checked
- [ ] Documentation is updated if required

## Context Refresh

If you lose context during implementation:
1. Re-read the step file: `.protocols/XXXX-*/YY-{step-name}.md`
2. Check the protocol plan: `.protocols/XXXX-*/plan.md`
3. Review relevant Memory Bank guides
4. Check current TodoWrite list

## Output Format

At the end of each session, provide:

```markdown
## Protocol XXXX Step YY Progress Report

### Completed Tasks
- [x] YY.1 Task name - Brief outcome
- [x] YY.2 Task name - Brief outcome

### In Progress
- [ ] YY.3 Task name - Current status, estimated completion

### Blockers
- Task YY.4 - Blocker description and suggested resolution

### Test Results
- Unit tests: X/Y passing
- Integration tests: Status
- Issues found: List

### Next Steps
1. Complete task YY.3
2. Resolve blocker for YY.4
3. Run full test suite

### Files Modified
- `path/to/file1.ts`
- `path/to/file2.tsx`
- `path/to/test.spec.ts`
```

## Target Audience

Assume the AI is assisting a **mid-level developer** who can:
- Understand technical context
- Implement features independently
- Make reasonable decisions about implementation details
- Ask for clarification when needed
