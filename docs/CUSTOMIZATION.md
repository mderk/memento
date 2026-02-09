# Customization Guide

Learn how to customize and extend your AI development environment.

## Important Note

This plugin uses **prompt-based generation**, meaning files are generated once from prompts by an LLM. After generation, you customize the **generated files** in your project, not the prompt templates in the plugin.

## Quick Customization Checklist

After running `/create-environment`, customize these files in priority order:

### ✅ Essential (Do these first)

-   [ ] `.memory_bank/product_brief.md` - Add your product vision and goals
-   [ ] `.memory_bank/tech_stack.md` - Verify and expand tech details
-   [ ] `.memory_bank/guides/getting-started.md` - Add setup instructions
-   [ ] `.memory_bank/guides/architecture.md` - Document your architecture

### 📝 Recommended (Do within first week)

-   [ ] `.memory_bank/guides/backend.md` - Add backend-specific patterns
-   [ ] `.memory_bank/guides/frontend.md` - Add frontend-specific patterns
-   [ ] `.memory_bank/guides/testing.md` - Document testing approach
-   [ ] `.memory_bank/patterns/api-design.md` - Customize API conventions
-   [ ] `.memory_bank/workflows/feature-development.md` - Adapt to your process

### 🎨 Optional (As needed)

-   [ ] `.memory_bank/guides/visual-design.md` - If you have a design system
-   [ ] `.memory_bank/current_tasks.md` - Start tracking tasks
-   [ ] Add custom agents to `.claude/agents/`
-   [ ] Add custom commands to `.claude/commands/`

## Customizing Core Documentation

### Product Brief

**File**: `.memory_bank/product_brief.md`

This file should answer:

-   What problem does your product solve?
-   Who are your target users?
-   What makes your solution unique?
-   What are the key features?

**Example customization**:

```markdown
# Product Brief: TaskMaster Pro

## Vision

TaskMaster Pro is the fastest, most intuitive task management app
for remote teams, combining simplicity with powerful automation.

## Target Users

### Primary: Remote Team Leads

-   Managing 5-20 people across timezones
-   Need visibility without micromanaging
-   Pain: Existing tools are too complex

### Secondary: Individual Contributors

-   Want simple task tracking
-   Need integration with existing tools
-   Pain: Context switching between apps

## Key Features

1. **Smart Task Routing** - AI suggests best person for each task
2. **Async Updates** - Daily digests instead of constant notifications
3. **Deep Integrations** - Works with Slack, GitHub, Figma
```

### Tech Stack

**File**: `.memory_bank/tech_stack.md`

Expand the auto-generated content with:

-   Specific versions and why
-   Architecture decisions
-   Third-party services
-   Infrastructure details

**Example additions**:

```markdown
## Backend

### Framework: FastAPI 0.104

**Why FastAPI?**

-   Need high performance for real-time features
-   Great async support
-   Auto-generated OpenAPI docs

### Database: PostgreSQL 15

**Schema approach**:

-   Using Alembic for migrations
-   Row-level security for multi-tenancy
-   JSONB for flexible task metadata

## Third-Party Services

### Authentication: Auth0

-   Social login (Google, GitHub, Microsoft)
-   SSO for enterprise customers
-   MFA support

### Email: SendGrid

-   Transactional emails
-   Email digest generation
-   Template management

### File Storage: AWS S3

-   Task attachments
-   User avatars
-   Export files
```

## Customizing Guides

### Architecture Guide

**File**: `.memory_bank/guides/architecture.md`

Document your specific architecture:

```markdown
## High-Level Architecture

'''
┌─────────────┐
│ Browser │
│ (React + │
│ MobX) │
└──────┬──────┘
│ HTTPS/WSS
▼
┌─────────────┐ ┌──────────────┐
│ FastAPI │─────▶│ PostgreSQL │
│ Server │ │ Database │
└──────┬──────┘ └──────────────┘
│
├───▶ Redis (Cache + Sessions)
├───▶ Celery (Background Tasks)
└───▶ AWS S3 (File Storage)
'''

## Component Interaction

### User Authentication Flow

1. User enters credentials in React app
2. App sends POST /auth/login to FastAPI
3. FastAPI validates with Auth0
4. Server creates session in Redis
5. Returns JWT to client
6. Client stores in memory (not localStorage)

### Real-Time Updates Flow

1. Client opens WebSocket connection
2. Server authenticates via JWT
3. Client subscribes to task updates
4. Background tasks use Redis pub/sub
5. WebSocket handler forwards to clients
```

### Backend Guide

**File**: `.memory_bank/guides/backend.md`

Add your backend-specific patterns:

```markdown
## Code Organization

'''
server/
├── app/
│ ├── models/ # SQLAlchemy models
│ ├── schemas/ # Pydantic schemas
│ ├── api/ # API endpoints
│ │ ├── v1/ # API version 1
│ │ └── deps.py # Dependencies
│ ├── core/ # Core functionality
│ │ ├── config.py
│ │ ├── security.py
│ │ └── celery_app.py
│ ├── services/ # Business logic
│ └── utils/ # Utilities
├── alembic/ # DB migrations
└── tests/ # Tests mirror app/
'''

## Common Patterns

### Dependency Injection

All endpoints use dependency injection:

'''python
from app.api.deps import get_current_user, get_db

@router.get("/tasks/{task_id}")
async def get_task(
task_id: UUID,
db: Session = Depends(get_db),
current_user: User = Depends(get_current_user)
) -> TaskDetail:
task = await task_service.get_task(db, task_id, current_user)
return task
'''

### Error Handling

Use custom exceptions:

'''python
from app.core.exceptions import NotFoundError, PermissionError

if not task:
raise NotFoundError(f"Task {task_id} not found")

if task.owner_id != current_user.id:
raise PermissionError("You don't have access to this task")
'''
```

## Adding Custom Agents

Create new AI agents for project-specific tasks.

### Example: Database Migration Agent

**File**: `.claude/agents/migration-helper.md`

```markdown
---
name: migration-helper
description: |
    Specialized agent for creating and reviewing database migrations.
    Ensures migrations are safe, reversible, and follow best practices.
capabilities:
    - Generate Alembic migration files
    - Review migrations for data loss risks
    - Suggest indexes and constraints
    - Validate migration reversibility
tools: [Bash, Read, Write, Grep]
model: sonnet
color: purple
---

# Database Migration Helper

I help create safe, reversible database migrations.

## When to Use Me

-   Creating new migrations
-   Reviewing existing migrations
-   Planning schema changes
-   Troubleshooting migration issues

## What I Check

### Safety

-   No data loss in down() migration
-   Proper handling of NULL values
-   Constraints don't break existing data

### Performance

-   Indexes on foreign keys
-   Concurrent index creation for production
-   Batch updates for large tables

### Best Practices

-   Descriptive migration names
-   Comments explaining complex changes
-   References Memory Bank patterns

## Example Usage

'''bash

# Generate new migration

/migration-helper create "add user preferences table"

# Review existing migration

/migration-helper review alembic/versions/abc123_add_indexes.py
'''
```

## Adding Custom Commands

Create commands for your specific workflows.

### Example: Deploy Command

**File**: `.claude/commands/deploy.md`

```markdown
---
description: Deploy application to staging or production
argument-hint: <environment>
---

# Deploy Application

Deploy the application to specified environment with safety checks.

## Usage

'''bash
/deploy staging
/deploy production
'''

## Workflow

### Pre-deployment Checks

1. Run tests: `pytest --cov=app`
2. Check migrations: `alembic check`
3. Lint code: `ruff check .`
4. Security scan: `bandit -r app/`

### Staging Deployment

1. Build Docker image
2. Push to registry
3. Update Kubernetes manifests
4. Apply with kubectl
5. Run smoke tests
6. Monitor logs

### Production Deployment

1. All staging checks pass
2. Create git tag
3. Require manual approval
4. Blue-green deployment
5. Gradual traffic shift
6. Automated rollback if errors

## Safety

-   Never deploy directly to production
-   Always test in staging first
-   Monitor error rates after deployment
-   Have rollback plan ready
```

### Example: Database Backup Command

**File**: `.claude/commands/backup-db.md`

```markdown
---
description: Create database backup and verify integrity
argument-hint: [environment]
---

# Database Backup

Create and verify database backup for specified environment.

## Usage

'''bash

# Backup development database

/backup-db dev

# Backup production database (requires confirmation)

/backup-db production
'''

## Workflow

1. Check disk space
2. Stop write-intensive cron jobs
3. Create pg_dump backup
4. Compress with gzip
5. Upload to S3
6. Verify backup integrity
7. Update backup inventory
8. Resume cron jobs
9. Send notification
   '''
```

## Customizing Workflows

### Feature Development Workflow

**File**: `.memory_bank/workflows/feature-development.md`

Adapt to your team's process:

```markdown
## Our Feature Development Process

### Phase 1: Planning (1-2 days)

1. Product creates PRD using `/create-prd`
2. Team reviews in stand-up
3. Engineering creates spec using `/create-spec`
4. Design creates mockups (if UI changes)
5. Team reviews spec, approves

### Phase 2: Implementation (1-2 weeks)

1. Dev implements following test-driven approach:
    - Write tests first
    - Implement feature
    - Code review with `/code-review`
    - Run tests with `/run-tests`
3. Daily updates in `.memory_bank/current_tasks.md`

### Phase 3: QA (2-3 days)

1. Deploy to staging
2. QA runs test plan
3. Design reviews UI (if applicable) using `@design-reviewer`
4. Product validates requirements
5. Fix any issues

### Phase 4: Release (1 day)

1. Create release notes
2. Deploy to production
3. Monitor metrics
4. Update docs
5. Create COMPLETION_SUMMARY.md
   '''
```

## Advanced Customization

### Regenerating Files

If you want to regenerate files after updating your tech stack:

1. Delete the files you want to regenerate (or entire `.memory_bank/` and `.claude/`)
2. Run `/create-environment` again
3. The agent will detect the new/changed stack and generate accordingly

**Tip**: Keep a backup of customizations before regenerating.

### Creating Custom Prompt Files

For plugin developers: You can create new prompt files in `prompts/` directory:

**Example**: `prompts/memory_bank/guides/custom-guide.md.prompt`

```yaml
---
file: custom-guide.md
target_path: .memory_bank/guides/
priority: 99
dependencies: []
conditional: null
---
# Generation Instructions for guides/custom-guide.md

Your custom generation instructions here...
```

### Adding Static Files (Plugin Development)

For plugin developers: You can add universal content that doesn't need LLM adaptation.

Static files are copied as-is to all projects (no generation, no placeholders).

**When to use static files:**

-   Universal workflows (e.g., code review checklist, git workflow)
-   Reference documentation that applies to all projects
-   Checklists and templates that don't need tech-specific adaptation

**How to add static files:**

1. Add your file to `static/memory_bank/` directory:
    - `static/memory_bank/guides/` - Universal guides
    - `static/memory_bank/workflows/` - Universal workflows
    - `static/memory_bank/patterns/` - Universal patterns

2. Register in `static/manifest.yaml`:

```yaml
files:
    - source: memory_bank/guides/code-review-checklist.md
      target: .memory_bank/guides/code-review-checklist.md
      conditional: null # always copy

    - source: memory_bank/workflows/ruby-workflow.md
      target: .memory_bank/workflows/ruby-workflow.md
      conditional: "backend_language == 'Ruby'" # conditional copy
```

**Available conditional expressions:**

-   `null` - Always copy (universal content)
-   `"has_frontend"` - Only if frontend detected
-   `"backend_language == 'Ruby'"` - Only for Ruby projects
-   `"has_tests && has_ci"` - Multiple conditions

**Example static file**: `static/memory_bank/guides/code-review-checklist.md`

```markdown
# Code Review Checklist

Universal checklist for conducting effective code reviews.

## Before Reviewing

-   [ ] Understand the context
-   [ ] Check the scope
    ...
```

Static files are copied before prompt-based generation in Phase 2.

### Team-Wide Configuration

Share configuration with your team:

**File**: `.claude/plugin-config.json`

```json
{
    "memento": {
        "templates": {
            "product_brief": ".claude/templates/custom-prd.md",
            "tech_stack": ".claude/templates/custom-stack.md"
        },
        "agents": {
            "test-runner": {
                "coverage-threshold": 80,
                "fail-on-warning": true
            }
        },
        "commands": {
            "prime": {
                "files": [
                    ".memory_bank/README.md",
                    ".memory_bank/product_brief.md",
                    ".memory_bank/tech_stack.md",
                    ".memory_bank/guides/architecture.md",
                    "CUSTOM_GUIDELINES.md"
                ]
            }
        }
    }
}
```

Commit this file so your team shares the same configuration.

## Best Practices

### 1. Keep Documentation Current

-   Update docs when you change code
-   Use `/sync-docs` (v1.1.0+) to detect drift
-   Review Memory Bank monthly

### 2. Use Relative Links

Always use relative links in documentation:

```markdown
<!-- Good -->

See [Architecture Guide](./guides/architecture.md)

<!-- Bad -->

See [Architecture Guide](/Users/me/project/.memory_bank/guides/architecture.md)
```

### 3. Version Control

Commit these to git:

-   `.memory_bank/` (all documentation)
-   `.claude/` (agents and commands)
-   `CLAUDE.md` (onboarding)

Ignore these:

-   `.memory_bank/.metadata.json` (generated metadata)
-   `.memory_bank/current_tasks.md` (personal task tracking)

### 4. Team Guidelines

Document your team's conventions:

**File**: `.memory_bank/guides/team-conventions.md`

```markdown
# Team Conventions

## Code Style

-   Use Black formatter (line length: 100)
-   Follow PEP 8
-   Type hints required for public functions

## Git Workflow

-   Feature branches from `main`
-   PR requires 1 approval
-   Squash merge to main
-   Conventional commits (feat:, fix:, docs:)

## Testing

-   Minimum 80% coverage
-   Integration tests required for APIs
-   E2E tests for critical paths

## Documentation

-   Update Memory Bank with architectural changes
-   Document breaking changes in CHANGELOG.md
-   Update API docs when endpoints change
    '''
```

## Troubleshooting Customizations

### Broken Links

If navigation links break after customizing:

1. Check relative link paths in markdown files
2. Ensure referenced files exist
3. Use format: `[Link Text](./relative/path.md)`

### Outdated Content

If your generated files seem outdated:

1. Delete outdated files
2. Run `/create-environment` again to regenerate
3. The agent will use latest prompts and detect current stack

### Inconsistent Structure

If Memory Bank structure seems inconsistent:

1. Check all required files are present (see docs/SPECIFICATION.md)
2. Regenerate missing files by running command again
3. Agent will detect missing files and generate only those

## Getting Help

-   **Issues**: [GitHub Issues](https://github.com/yourusername/memento/issues)
-   **Discussions**: [GitHub Discussions](https://github.com/yourusername/memento/discussions)
-   **Documentation**: [README.md](../README.md)

---

**Make it yours!** The AI environment works best when customized for your specific project and team.
