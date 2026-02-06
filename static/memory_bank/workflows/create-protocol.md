# Create Protocol Workflow

## Goal

Generate a structured protocol with Architecture Decision Record (ADR) and step files from a PRD for complex features requiring multi-phase implementation.

## When to Use

-   Complex features requiring multiple implementation phases
-   Major refactorings needing architectural context
-   Cross-cutting changes affecting multiple subsystems
-   Long-running work needing progress tracking across sessions

## Protocol Structure

```
.protocols/
└── NNNN-protocol-name/
    ├── plan.md          # Mini-ADR: Context, Decision, Rationale
    ├── 01-step-name.md    # First implementation step
    ├── 02-step-name.md    # Second implementation step
    └── ...
```

## Protocol language

```
Protocol language: English, unless specified otherwise explicitly.
```

## Process

### Step 1: Create Protocol Directory

```bash
mkdir -p .protocols/0001-feature-name
```

Use sequential numbering: 0001, 0002, etc.

### Step 2: Create Mini-ADR (plan.md)

```markdown
# Protocol: [Feature Name]

**Status**: Draft | In Progress | Complete
**Created**: YYYY-MM-DD
**PRD**: [Link to PRD]

## Context

What problem are we solving? Why is this change needed?

-   Current state
-   Pain points
-   Business drivers

## Decision

What approach are we taking?

-   High-level solution
-   Key architectural choices
-   Trade-offs considered
-   **Testability**: How will this be tested? (unit/integration/e2e)

## Rationale

Why this approach over alternatives?

-   Alternative 1: Pros/Cons
-   Alternative 2: Pros/Cons
-   Chosen approach: Why it's best for our context

## Consequences

What are the implications?

### Positive

-   Benefit 1
-   Benefit 2

### Negative

-   Drawback 1 (and mitigation)
-   Drawback 2 (and mitigation)

### Neutral

-   Change 1
-   Change 2

## Implementation Steps

1. [Step 1 Name](./01-step-name.md) - Brief description
2. [Step 2 Name](./02-step-name.md) - Brief description
3. [Step 3 Name](./03-step-name.md) - Brief description

## Progress

-   [ ] Step 1: Not started
-   [ ] Step 2: Not started
-   [ ] Step 3: Not started
```

### Step 3: Create Step Files

For each implementation step:

````markdown
# Step 01: [Step Name]

**Status**: Not Started | In Progress | Complete
**Estimated**: X hours
**Actual**: X hours (filled after completion)
**depends_on**: [00-previous-step] (or [] if none)

## Objective

What does this step accomplish?

## Prerequisites

-   Previous steps completed
-   Required dependencies
-   Any setup needed

## Tasks

### Task 1: [Task Name]

-   [ ] 1.1: Subtask description
-   [ ] 1.2: Subtask description
-   [ ] 1.3: Subtask description

### Task 2: [Task Name]

-   [ ] 2.1: Subtask description
-   [ ] 2.2: Subtask description

### Tests (required for each task)

-   [ ] T1: Tests for Task 1
-   [ ] T2: Tests for Task 2

## Implementation Notes

Key considerations for this step:

-   Pattern to follow
-   Files to modify
-   **How to test**: What tests to write, what to mock, test data needed

## Memory Bank Impact

Expected documentation updates (review at protocol end):

-   [ ] Pattern: [description] → [target file]
-   [ ] None expected

## Verification

How to verify this step is complete:

```bash
npm run test:run
npm run e2e
```
````

-   [ ] All tests pass
-   [ ] Code review complete
-   [ ] Documentation updated

## Next Step

After completion, proceed to [Step 02](./02-step-name.md)

````

### Step 4: Review Protocol

Before proceeding:

- [ ] ADR clearly explains context and decision
- [ ] Steps are properly sequenced
- [ ] Dependencies identified
- [ ] Estimates provided
- [ ] Verification criteria defined

## Command

```bash
/create-protocol path/to/prd.md
````

The AI will:

1. Read the PRD
2. Create protocol directory
3. Generate mini-ADR
4. Create step files
5. Return protocol summary

## Example Protocol

For "PostgreSQL Migration" feature:

```
.protocols/0001-postgresql-migration/
├── README.md
├── 01-schema-definition.md
├── 02-prisma-client-setup.md
├── 03-api-route-migration.md
├── 04-data-migration-script.md
├── 05-testing-validation.md
└── 06-production-cutover.md
```

**README.md excerpt:**

```markdown
# Protocol: PostgreSQL Migration

**Status**: In Progress
**Created**: 2025-12-25

## Context

MongoDB lacks referential integrity and proper foreign key support.
Multi-tenant data isolation relies on application-level checks.
Type safety is limited without a proper ORM.

## Decision

Migrate to PostgreSQL with Prisma ORM.

## Rationale

PostgreSQL + Prisma provides:

-   Referential integrity with foreign keys
-   Type-safe database queries
-   Better tooling (Prisma Studio, migrations)
-   Row Level Security for multi-tenancy

## Implementation Steps

1. [Schema Definition](./01-schema-definition.md) - Create Prisma schema
2. [Client Setup](./02-prisma-client-setup.md) - Configure Prisma client
3. [API Migration](./03-api-route-migration.md) - Update API routes
4. [Data Migration](./04-data-migration-script.md) - Migrate existing data
5. [Testing](./05-testing-validation.md) - Validate migration
6. [Cutover](./06-production-cutover.md) - Production deployment
```

## Best Practices

### DO

-   Keep ADR focused and concise
-   Break into logical, independent steps
-   Include verification criteria
-   Link steps to each other
-   Update progress as you work

### DON'T

-   Create too many small steps
-   Skip the rationale section
-   Forget to update status
-   Proceed without verification
-   Ignore consequences section

## Related Documentation

-   [Process Protocol](./process-protocol.md) - Execute protocol steps
-   [Feature Workflow](./feature-workflow.md) - Full feature development
-   [Generate Tasks](./generate-tasks.md) - Alternative for simpler features
