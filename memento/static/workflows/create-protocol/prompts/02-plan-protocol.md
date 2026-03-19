# Plan Protocol Structure

Create a structured protocol plan from the PRD and project context.

## PRD

Read the PRD file:

`{{variables.protocol_dir}}/prd.md`

## Project Context

Read the project's Memory Bank for context:

- `.memory_bank/README.md` — project overview and navigation
- `.memory_bank/product_brief.md` — project description
- `.memory_bank/tech_stack.md` — technical architecture

Read relevant guides if referenced in the PRD:

- `.memory_bank/patterns/index.md` — development patterns
- `.memory_bank/guides/index.md` — implementation guides

## Instructions

Design a protocol that breaks the PRD into focused, sequentially-executable steps.

### Protocol structure rules

1. **Steps execute sequentially** in a single git worktree — order by dependency
2. **Each step** should be independently verifiable (has its own verification commands)
3. **Group steps** into directories when they logically belong together or need scoped context
4. **Each task group** within a step becomes one TDD unit — keep them focused (1-3 hours each)
5. **Estimate realistically** — include time for tests, not just implementation

### What goes where

- **`name`**: human-readable, action-oriented (e.g., "Setup database schema", not "Database")
- **`objective`**: WHY this step exists and WHAT it accomplishes (1-3 sentences)
- **`tasks`**: list of task groups. Each task is a coherent unit of work (one TDD cycle, 1-3 hours). A task has a `heading` (concise, action-oriented) and `subtasks` — the concrete items to implement. Subtasks can have a `body` (detailed description, examples) and nested `subtasks` for sub-items
- **`constraints`**: acceptance criteria / definition of done for this step
- **`verification`**: shell commands that prove the step works (tests, type checks, build commands)
- **`starting_points`**: key source files the developer should read first
- **`context_files`**: Memory Bank files or `_context/` files relevant to this step
- **`impl_notes`**: patterns to follow, key decisions, gotchas

### ADR section

The ADR (context, decision, rationale, consequences) should be concise:
- **Context**: 1-3 sentences summarizing the problem
- **Decision**: what approach and why (link to prd.md for full requirements)
- **Rationale**: why this approach over alternatives (list alternatives considered)
- **Consequences**: be honest about trade-offs

### Item ordering

Use `items` array with discriminated union:
- `{"type": "step", "step": {...}}` for root-level steps
- `{"type": "group", "group": {"title": "...", "steps": [...]}}` for grouped steps

## Rich text fields

Fields marked "rich text" in the schema support full formatting. Use them to give the developer detailed, readable instructions. Examples of what rich text values should look like:

**`objective`** — lists, emphasis:

    Consolidate the notification delivery pipeline into a single service:

    - **Email**: migrate from per-handler SMTP calls to queued delivery
    - **Push**: replace Firebase direct calls with the unified queue
    - **SMS**: add as a new channel using the same queue infrastructure

**`body`** (in a subtask) — code examples, references:

    Add a `deliver()` method that routes by channel type.

    ```python
    class NotificationService:
        def deliver(self, notification: Notification) -> DeliveryResult:
            handler = self._handlers[notification.channel]
            return handler.send(notification)
    ```

    See `services/email.py` for the existing pattern to follow.

**`impl_notes`** — tables, key decisions:

    Channel routing strategy:

    | Channel | Handler class | Queue priority |
    |---------|--------------|----------------|
    | email   | SmtpHandler  | normal         |
    | push    | FcmHandler   | high           |
    | sms     | TwilioHandler| normal         |

    Use the existing `BaseHandler` ABC — don't create a new interface.

Plain text fields (`name`, `heading`, `title`) are one-liners — no formatting.

## Output

Respond with a JSON object matching the ProtocolPlan schema.
