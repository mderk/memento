---
name: detect-tech-stack
description: Detect project tech stack (frameworks, databases, test frameworks, libraries) and output structured JSON
version: 1.0.0
---

# Detect Tech Stack Skill

## Purpose

Automatically detect project technologies by analyzing dependency files and project structure. Returns structured JSON with framework versions, databases, test frameworks, and libraries.

## When Claude Uses This Skill

Claude automatically invokes this skill when:

1. **Creating environment**: `/create-environment` needs to detect tech stack for first time
2. **Updating environment**: `/update-environment auto` needs to re-detect for comparison
3. **User requests detection**: "What tech stack does this project use?"
4. **Analyzing project**: "Analyze my project structure"

## Invocation

From target project, run:

```bash
python ${CLAUDE_PLUGIN_ROOT}/skills/detect-tech-stack/scripts/detect.py
```

## Usage

### Automatic Invocation

```
User: /create-environment

Claude: I'll detect your project's tech stack first.
[Automatically invokes detect-tech-stack skill]

Tech Stack Detected:
- Backend: Django 5.0.1 (Python)
- Frontend: React 18.2.0 + Next.js 14.0.0
- Database: PostgreSQL 15.3
- Tests: pytest, jest, playwright
```

### Manual Invocation (by user)

User can run the slash command directly:
```bash
# This will be registered if skill provides a command
/detect-tech-stack
```

Or ask Claude to analyze:
```
User: What technologies does my project use?
Claude: [Invokes detect-tech-stack skill automatically]
```

## How It Works

The skill executes `scripts/detect.py` which:

1. **Scans dependency files**:
   - Python: `requirements.txt`, `pyproject.toml`, `Pipfile`
   - JavaScript: `package.json`
   - Go: `go.mod`
   - Ruby: `Gemfile`
   - Java: `pom.xml`, `build.gradle`
   - PHP: `composer.json`

2. **Detects frameworks and versions**:
   - Backend: Django, FastAPI, Flask, Express, NestJS, Gin, Rails, Spring Boot, Laravel
   - Frontend: React, Vue, Angular, Svelte (+ meta-frameworks: Next.js, Nuxt, SvelteKit)
   - Databases: PostgreSQL, MySQL, MongoDB, SQLite, Redis, MariaDB
   - Test Frameworks: pytest, jest, vitest, playwright, cypress, mocha

3. **Analyzes project structure**:
   - Monorepo detection (lerna, pnpm workspaces, turborepo)
   - Docker setup (Dockerfile, docker-compose.yml)
   - CI/CD (GitHub Actions, GitLab CI, CircleCI)
   - Deployment platforms (Vercel, Netlify, Render)

4. **Outputs structured JSON**:
   ```json
   {
     "project_name": "example-app",
     "detected_at": "2025-12-18T10:30:00Z",
     "backend": {
       "framework": "Django",
       "version": "5.0.1",
       "language": "Python",
       "has_backend": true
     },
     "frontend": {
       "framework": "React",
       "version": "18.2.0",
       "meta_framework": "Next.js",
       "meta_version": "14.0.0",
       "has_frontend": true
     },
     "database": {
       "primary": "PostgreSQL",
       "version": "15.3",
       "cache": "Redis"
     },
     "testing": {
       "frameworks": ["pytest", "jest", "playwright"],
       "has_tests": true,
       "has_e2e_tests": true
     },
     "libraries": {
       "state_management": "Redux",
       "orm": "Prisma",
       "ui_library": "Material-UI",
       "api_client": "axios"
     },
     "structure": {
       "is_monorepo": false,
       "has_docker": true,
       "has_ci_cd": true,
       "ci_platform": "GitHub Actions",
       "deployment_platform": "Vercel"
     }
   }
   ```

## Output

### Success

```json
{
  "status": "success",
  "data": {
    "project_name": "...",
    "backend": {...},
    "frontend": {...},
    ...
  }
}
```

### Error

```json
{
  "status": "error",
  "message": "No dependency files found. Is this a code project?"
}
```

## Exit Codes

- `0`: Detection successful
- `1`: No dependency files found
- `2`: Invalid project structure
- `3`: Error reading files

## Integration with Commands

### /create-environment

```markdown
## Phase 1: Create Generation Plan

1. **Detect tech stack**: Invoke detect-tech-stack skill
   - Skill returns JSON with all detected technologies
   - Save to `.memory_bank/project-analysis.json`

2. **Analyze templates**: Use detected tech stack to filter relevant prompts
```

### /update-environment auto

```markdown
## Step 0.1: Analyze Current Project State

1. **Re-detect tech stack**: Invoke detect-tech-stack skill
   - Returns current state as JSON

2. **Load original state**: Read `.memory_bank/project-analysis.json`

3. **Compare states**: Identify changes (framework upgrades, new libraries, etc.)
```

## Example Scenarios

### Scenario 1: Django + React Project

```
Input: Project with package.json (react, next) and requirements.txt (django, psycopg2)

Output:
✓ Backend: Django 5.0.1 (Python)
✓ Frontend: React 18.2.0 + Next.js 14.0.0
✓ Database: PostgreSQL (from psycopg2)
✓ Tests: pytest, jest
✓ Docker: Yes (docker-compose.yml found)
```

### Scenario 2: Go Microservices

```
Input: Project with go.mod (gin, gorm, testify)

Output:
✓ Backend: Gin (Go)
✓ Database: PostgreSQL (from gorm)
✓ Tests: Go testing + testify
✓ Docker: Yes
✓ CI/CD: GitHub Actions
```

### Scenario 3: Monorepo

```
Input: pnpm-workspace.yaml, multiple package.json files

Output:
✓ Monorepo: Yes (pnpm workspaces)
✓ Frontend: React (apps/web), Vue (apps/admin)
✓ Backend: Express.js (apps/api)
✓ Shared packages detected: 3
```

## Script Location

```
./scripts/detect.py
```

## Dependencies

- Python 3.7+
- Standard library only (json, pathlib, re, datetime)
- No external dependencies required

## Testing

Run detection manually:
```bash
cd /path/to/project
python ./scripts/detect.py
```

Output will be printed as JSON to stdout.

## Notes

- Detection is **non-invasive** (read-only, no file modifications)
- Handles missing files gracefully (returns null for undetected items)
- Version extraction uses regex for common version formats
- Supports multiple dependency files (e.g., both requirements.txt and package.json)
