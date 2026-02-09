# Memory Bank Anti-Patterns Reference

This document lists common redundancy patterns found in generated Memory Bank files and how to avoid them. Use this as a checklist when creating new prompts or optimizing existing ones.

**Target Audience:** Prompt engineers and the environment-generator agent

---

## Table of Contents

**General Anti-Patterns (1-12)** - Apply to all Memory Bank content:

1. [Template Repetition](#1-template-repetition) - Same structure 2+ times (60-70% savings)
2. [Code Example Redundancy](#2-code-example-redundancy) - Multiple variations (70% savings)
3. [Checklist Duplication](#3-checklist-duplication) - Overlapping checklists (65% savings)
4. [Concept Re-Explanation](#4-concept-re-explanation) - Same concept 2+ times (75% savings)
5. [Verbose Boilerplate](#5-verbose-boilerplate) - Static "What is X?" (40% savings)
6. [Excessive Example Diversity](#6-excessive-example-diversity) - 5+ similar examples (60% savings)
7. [Over-Explaining Obvious Operations](#7-over-explaining-obvious-operations) - Obvious commands (85% savings)
8. [Directory Structure Duplication](#8-directory-structure-duplication) - Directory tree 2+ times (70% savings)
9. [Redundant Before/After Examples](#9-redundant-beforeafter-examples) - More than 2 pairs (50% savings)
10. [Framework Documentation Redundancy](#10-framework-documentation-redundancy) - Well-known tech (80% savings)
11. [Troubleshooting Redundancy](#11-troubleshooting-redundancy) - Restating best practices (60% savings)
12. [Severity Level Repetition](#12-severity-level-repetition) - Defined locally (75% savings)

**Specialized Anti-Patterns (13-25)** - Specific to agents/commands/patterns:
13. [Agent: Inline Documentation Instead of References](#13-agent-specific-anti-patterns) - Duplicates guides (70-80% savings)
14. [Agent: Report Format Template Bloat](#14-report-format-template-bloat) - 60+ line templates (80% savings)
15. [Test-Runner: Command Duplication](#15-command-duplication-in-process-steps) - Same commands 2+ times (60% savings)
16. [Pattern: Framework-Specific Bloat](#16-framework-specific-bloat-in-generic-files) - Unused framework examples (85% savings)
17. [Workflow: Over-Detailed Specification Examples](#17-over-detailed-specification-examples) - 200+ line examples (70% savings)
18. [Command: Meta-Instruction Inflation](#18-meta-instruction-inflation-in-commands) - 3+ overlapping checklists (70% savings)
19. [Placeholder Status Disclaimers](#19-placeholder-status-disclaimers) - "Not configured yet" messages (100% clarity improvement)
20. [Workflow-Guide Confusion](#20-workflow-guide-confusion) - Workflows embed guide content (70-80% savings)
21. [Completeness Bloat](#21-completeness-bloat) - Self-contained over reference-first (60-70% savings)
22. [Lost Interaction Models](#22-lost-interaction-models) - Critical user interaction patterns disappear (UX preservation)
23. [Hardcoded Tech in Prompts](#23-hardcoded-tech-in-prompts) - Technology examples in project-agnostic prompts (project-agnostic compliance)
24. [Self-Contained Over Reference-First](#24-self-contained-over-reference-first) - Documents try to be complete vs connected (50-70% savings)
25. [Descriptive Workflows Instead of Prescriptive Rules](#25-descriptive-workflows-instead-of-prescriptive-rules) - Explains instead of instructs (50% savings)

**Quick Reference:**

-   [Detection Checklist](#anti-pattern-detection-checklist-updated) - Check all 25 items
-   [Optimization Targets by File Type](#optimization-targets-by-file-type-updated) - Agents, Commands, Patterns, Workflows

---

# General Anti-Patterns (1-12)

## 1. Template Repetition

### ❌ Anti-Pattern: Showing complete examples multiple times

**Problem:**

```markdown
## Output Requirements

[Full 200-line template]

## Example Output

[Same 200-line template again]

## Validation

[Checking against same template a third time]
```

**Impact:** 2-3x redundancy in prompts, generates identical boilerplate

### ✅ Best Practice: Single canonical template

```markdown
## Output Requirements

[Full template once]

## Example Output

See Output Requirements section above.

## Validation

-   [ ] Follows template in Output Requirements
```

**Savings:** 60-70% reduction in prompt size

---

## 2. Code Example Redundancy

### ❌ Anti-Pattern: Multiple variations of same pattern

**Problem:**

```python
# Example 1: User creation
try:
    user = create_user(data)
    return success(user)
except ValueError:
    return error("Invalid", 400)

# Example 2: Product creation
try:
    product = create_product(data)
    return success(product)
except ValueError:
    return error("Invalid", 400)

# Example 3: Order creation
try:
    order = create_order(data)
    return success(order)
except ValueError:
    return error("Invalid", 400)
```

**Impact:** 3x redundancy, same pattern repeated

### ✅ Best Practice: One comprehensive example

```python
# Generic CRUD pattern - adapt for your entity
try:
    entity = create_entity(data)  # user/product/order
    return success(entity)
except ValueError as e:
    return error(f"Invalid {entity_type}", 400)
except Exception as e:
    logger.exception("Creation failed")
    return error("Internal error", 500)

# Variations:
# - Replace create_entity with specific function
# - Add entity-specific validation
# - Customize error messages
```

**Savings:** 70% reduction, single pattern covers all cases

---

## 3. Checklist Duplication

### ❌ Anti-Pattern: Separate overlapping checklists

**Problem:**

```markdown
## Quality Checklist

-   [ ] Code follows standards
-   [ ] Tests included
-   [ ] Documentation updated

## Common Mistakes to Avoid

-   Missing tests
-   Outdated documentation
-   Non-standard code

## Validation

-   [ ] Code standards verified
-   [ ] Test coverage checked
-   [ ] Docs synchronized
```

**Impact:** Same items repeated 3 times with different wording

### ✅ Best Practice: Consolidated checklist

```markdown
## Quality Checklist

**Code Quality:**

-   [ ] Follows project standards
-   [ ] No common anti-patterns

**Testing:**

-   [ ] Unit tests included (>80% coverage)
-   [ ] Edge cases covered

**Documentation:**

-   [ ] Inline comments for complex logic
-   [ ] README updated if API changed
-   [ ] Memory Bank docs synchronized
```

**Savings:** 65% reduction, eliminates redundancy

---

## 4. Concept Re-Explanation

### ❌ Anti-Pattern: Explaining same concept multiple times

**Problem:**

```markdown
## Overview

The AAA pattern (Arrange-Act-Assert) structures tests...

## Writing Tests

Remember to use AAA pattern: Arrange your data, Act...

## Best Practices

Always follow AAA (Arrange-Act-Assert) pattern...

## Examples

# This test uses AAA pattern

# Arrange: setup

# Act: execute

# Assert: verify
```

**Impact:** Concept explained 4 times

### ✅ Best Practice: Explain once, reference elsewhere

```markdown
## Testing Principles

**AAA Pattern:** All tests follow Arrange-Act-Assert:

1. **Arrange:** Set up test data
2. **Act:** Execute code under test
3. **Assert:** Verify expected outcome

## Writing Tests

Follow the AAA pattern (see Testing Principles above).

## Examples

# AAA pattern example

data = setup_data() # Arrange
result = function(data) # Act
assert result == expected # Assert
```

**Savings:** 75% reduction, cross-references prevent duplication

---

## 5. Verbose Boilerplate

### ❌ Anti-Pattern: Static explanatory text in every file

**Problem:**

```markdown
# Every index.md file:

## What are Guides?

Guides are in-depth documentation that explain...
[50 lines of identical text in guides/index.md]

# Also in workflows/index.md:

## What are Workflows?

Workflows are step-by-step processes...
[50 lines of similar explanatory text]
```

**Impact:** Static content repeated across files

### ✅ Best Practice: Template variables for static content

```markdown
# In prompt:

## What are Guides?

{{GUIDES_EXPLANATION}}

# In reusable-blocks.md:

## {{GUIDES_EXPLANATION}}

Guides are in-depth documentation covering architecture,
development patterns, and best practices. [concise version]
```

**Savings:** 40% reduction, centralized maintenance

---

## 6. Excessive Example Diversity

### ❌ Anti-Pattern: Too many similar examples

**Problem:**

```markdown
## Task Examples

### Task 1: Setup Database

...

### Task 2: Setup Authentication

...

### Task 3: Setup Email Service

...

### Task 4: Setup Logging

...

### Task 5: Setup Caching

...

### Task 6: Setup Queue

...

### Task 7: Setup Storage

...

### Task 8: Setup Monitoring

...
```

**Impact:** 8 tasks with identical structure, different domain

### ✅ Best Practice: Representative samples

```markdown
## Task Examples

### Example 1: Foundation (Database Setup)

[Comprehensive example showing full task structure]

### Example 2: Integration (Third-party Service)

[Shows integration-specific patterns]

### Example 3: Infrastructure (Monitoring)

[Shows deployment/ops patterns]

**Note:** Adapt these patterns for other tasks (auth, email, etc.)
```

**Savings:** 60% reduction, 3 examples vs 8

---

## 7. Over-Explaining Obvious Operations

### ❌ Anti-Pattern: Verbose explanations of basic commands

**Problem:**

````markdown
## Install Dependencies

First, we need to install the project dependencies. This
will download all required packages from PyPI and install
them into your virtual environment. The command will read
the requirements.txt file and install each package listed:

```bash
pip install -r requirements.txt
```
````

This command uses pip, the Python package installer, to
install (-i flag) packages from the requirements file (-r).

````

**Impact:** 8 lines to explain `pip install`

### ✅ Best Practice: Concise command reference

```markdown
## Install Dependencies

```bash
pip install -r requirements.txt
````

**Note:** First-time setup may take 2-3 minutes.

````

**Savings:** 85% reduction for obvious commands

---

## 8. Directory Structure Duplication

### ❌ Anti-Pattern: Showing same structure multiple times

**Problem:**
```markdown
## In architecture.md:
project/
├── backend/
│   ├── models/
│   └── views/

## In backend.md:
project/
├── backend/
│   ├── models/
│   └── views/

## In getting-started.md:
project/
├── backend/
│   ├── models/
│   └── views/
````

**Impact:** Directory tree shown 3+ times

### ✅ Best Practice: Show once, reference elsewhere

```markdown
## In architecture.md:

[Complete directory structure]

## In backend.md:

Backend code lives in `/backend` (see Architecture Guide
for complete project structure).

## In getting-started.md:

Refer to Architecture Guide for directory layout.
```

**Savings:** 70% reduction, single source of truth

---

## 9. Redundant "Before/After" Examples

### ❌ Anti-Pattern: Multiple before/after pairs for same concept

**Problem:**

```markdown
## Bad: Missing error handling

def function1(): ...

## Good: With error handling

def function1():
try: ...

## Bad: No logging

def function2(): ...

## Good: With logging

def function2():
logger.info()...

## Bad: No validation

def function3(): ...

## Good: With validation

def function3():
if not valid(): ...
```

**Impact:** 6 code blocks to show 3 concepts

### ✅ Best Practice: Comprehensive before/after

```markdown
## Before: Multiple issues

def process_data(data):
result = expensive_operation(data)
return result

## After: Best practices applied

def process_data(data): # Validation
if not is_valid(data):
raise ValueError("Invalid data")

    # Logging
    logger.info(f"Processing {len(data)} items")

    # Error handling
    try:
        result = expensive_operation(data)
        return result
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        raise
```

**Savings:** 50% reduction, single comprehensive example

---

## 10. Framework Documentation Redundancy

### ❌ Anti-Pattern: Explaining well-known frameworks

**Problem:**

```markdown
## What is MongoDB?

MongoDB is a NoSQL database that stores data in flexible,
JSON-like documents. Unlike traditional relational databases,
MongoDB doesn't require a predefined schema...
[20 lines explaining MongoDB basics]

## Connection Pooling

Connection pooling is a technique where database connections
are reused rather than created fresh for each request...
[15 lines explaining connection pooling]
```

**Impact:** Explaining concepts developers should know

### ✅ Best Practice: Assume technical knowledge

```markdown
## Database: MongoDB 5.0

**Configuration:**

-   Connection pool size: 10-50 (adjusted per load)
-   Index strategy: See schema models for indexes
-   Replica set for high availability

**Project-Specific Patterns:**

-   [Unique pattern or configuration]
-   [Non-standard usage]

**Documentation:** [MongoDB official docs](link)
```

**Savings:** 80% reduction, focus on project specifics

---

## 11. Troubleshooting Redundancy

### ❌ Anti-Pattern: Troubleshooting sections restate best practices

**Problem:**

```markdown
## Best Practices

-   Write tests for all new code
-   Keep functions under 50 lines
-   Use meaningful variable names

## Troubleshooting

**Problem:** Tests failing
**Solution:** Make sure you write tests for all new code

**Problem:** Function too complex
**Solution:** Keep functions under 50 lines

**Problem:** Code hard to understand
**Solution:** Use meaningful variable names
```

**Impact:** Same advice repeated as problems/solutions

### ✅ Best Practice: Unique troubleshooting insights

```markdown
## Best Practices

[Standard practices]

## Troubleshooting

**Problem:** `ModuleNotFoundError` after dependency update
**Cause:** Virtual environment not rebuilt
**Solution:** `rm -rf venv && python -m venv venv && pip install -r requirements.txt`

**Problem:** Tests pass locally but fail in CI
**Cause:** Timezone differences or missing environment variables
**Solution:** Check CI logs for specific error, ensure `.env.test` committed

[Only non-obvious, specific issues]
```

**Savings:** 60% reduction, avoid restating best practices

---

## 12. Severity Level Repetition

### ❌ Anti-Pattern: Defining severity levels in every file

**Problem:**

-   code-review-workflow.md: defines [CRITICAL], [REQUIRED], [SUGGESTION]
-   code-review-guidelines.md: same definitions
-   agent-orchestration.md: same definitions
-   bug-fix-workflow.md: same definitions

**Impact:** 4 files × 20 lines = 80 lines of duplicated content

### ✅ Best Practice: Template variable

```markdown
# In all prompts:

## Severity Levels

{{SEVERITY_LEVELS}}

# In reusable-blocks.md:

Single definition referenced by all files
```

**Savings:** 75% reduction, single source of truth

---

## Anti-Pattern Detection Checklist

When reviewing a generated file, check for:

-   [ ] **Template repetition:** Same structure shown 2+ times?
-   [ ] **Code examples:** More than 2 similar examples?
-   [ ] **Checklists:** Multiple checklists with overlapping items?
-   [ ] **Concept re-explanation:** Same concept explained 2+ times?
-   [ ] **Verbose boilerplate:** Static "What is X?" sections?
-   [ ] **Example diversity:** 5+ examples with similar structure?
-   [ ] **Over-explanation:** Obvious commands explained verbosely?
-   [ ] **Structure duplication:** Directory tree shown 2+ times?
-   [ ] **Before/After pairs:** More than 2 pairs for same concept?
-   [ ] **Framework explanations:** Explaining well-known technologies?
-   [ ] **Troubleshooting redundancy:** Restating best practices as solutions?
-   [ ] **Severity definitions:** Defined locally vs template variable?

**Target:** Check all 12 items before approving generated content

---

## Optimization Targets by File Type

### Core Documentation (README, product_brief, tech_stack, current_tasks)

**Target reduction:** 30-60%
**Focus on:**

-   Template variables for static content
-   Eliminating duplicate templates
-   Consolidating "Recommended Setup" for unimplemented features

### Guides (architecture, backend, frontend, testing, etc.)

**Target reduction:** 35-65%
**Focus on:**

-   Code example economy (1-2 vs 3-4)
-   Checklist consolidation
-   Removing framework explanations

### Workflows (feature, bug-fix, code-review, testing, etc.)

**Target reduction:** 30-50%
**Focus on:**

-   Eliminating Before/After redundancy
-   Consolidating checklists
-   Using cross-references vs re-explanation

---

## Usage Guidelines for Agents

**When generating files:**

1. **Read this file first** before generating any Memory Bank content
2. **Check generated output** against all 12 anti-patterns
3. **Apply optimizations** before saving final file
4. **Target lengths:** Aim for 20-30% below prompt's stated max lines
5. **Quality over quantity:** Concise, focused content beats verbose explanations

**When optimizing existing files:**

1. **Scan for anti-patterns** using detection checklist
2. **Calculate redundancy** (actual lines / target lines)
3. **Apply fixes** starting with highest-impact anti-patterns
4. **Verify information preservation** - don't remove unique content
5. **Report savings** (lines before/after, % reduction)

---

## Quick Reference: Reduction Strategies

| Anti-Pattern               | Strategy                   | Expected Savings |
| -------------------------- | -------------------------- | ---------------- |
| Template Repetition        | Single canonical template  | 60-70%           |
| Code Example Redundancy    | 1 comprehensive example    | 70%              |
| Checklist Duplication      | Consolidated checklist     | 65%              |
| Concept Re-Explanation     | Explain once + cross-ref   | 75%              |
| Verbose Boilerplate        | Template variables         | 40%              |
| Excessive Examples         | 2-3 representative samples | 60%              |
| Over-Explaining Commands   | Concise reference          | 85%              |
| Directory Duplication      | Show once, reference       | 70%              |
| Before/After Pairs         | Single comprehensive pair  | 50%              |
| Framework Explanations     | Project-specific only      | 80%              |
| Troubleshooting Redundancy | Unique insights only       | 60%              |
| Severity Level Repetition  | Template variable          | 75%              |

**Average across all strategies:** 67% reduction potential

---

# Specialized Anti-Patterns (13-18)

These patterns are specific to agents, commands, patterns, and workflows.

---

## 13. Agent-Specific Anti-Patterns

### ❌ Anti-Pattern: Inline Documentation Instead of References

**Problem (Agents):**

```markdown
## Backend Review Focus

**Flask Patterns:**

-   Route handlers should validate input
-   Use blueprints for organization
-   Error handling with @app.errorhandler
-   Request validation with marshmallow
    ... [30 more lines of Flask best practices]

**Database Patterns:**

-   Use connection pooling
-   Implement proper indexing
-   Query optimization techniques
    ... [20 more lines]
```

**Impact:** Agents duplicate 50-100 lines from backend.md, tech_stack.md

### ✅ Best Practice: Reference Memory Bank Guides

```markdown
## Backend Review Focus

**Review against:**

-   [Backend Guide](../.memory_bank/guides/backend.md) - Flask patterns, database, API design
-   [Tech Stack](../.memory_bank/tech_stack.md) - Project-specific configurations

**Agent-specific focus:**

-   Architecture violations (services calling each other incorrectly)
-   Security issues (SQL injection, XSS, missing auth)
-   Performance anti-patterns (N+1 queries, missing indexes)
```

**Savings:** 70-80% reduction, single source of truth

**Key principle:** Agents REFERENCE guides, don't DUPLICATE them.

---

## 14. Report Format Template Bloat

### ❌ Anti-Pattern: Full Report Template in Agent Files

**Problem:**

```markdown
## Review Report Format

Use this exact format:

## Code Review Report - [Feature Name]

**Files Reviewed:**

-   path/to/file1.py
-   path/to/file2.py

**Summary:**
[Brief overview]

**Issues Found:**

### [CRITICAL] Issue Title

**File:** path/to/file.py:45
**Issue:** [Description]
**Impact:** [What could go wrong]
**Fix:** [How to fix]

### [REQUIRED] Issue Title

... [60 more lines showing every section]
```

**Impact:** 60-80 lines of boilerplate in EVERY agent

### ✅ Best Practice: Minimal Template Reference

```markdown
## Review Report Format

**Structure:** Issue type, File location, Description, Fix

**Example:**
```

### [CRITICAL] SQL Injection

**File:** api/users.py:45
**Fix:** Use parameterized queries

```

**See:** [Code Review Guidelines](../.memory_bank/guides/code-review-guidelines.md) for full format
```

**Savings:** 80% reduction (60 lines → 10 lines)

---

## 15. Command Duplication in Process Steps

### ❌ Anti-Pattern: Test Commands Shown Multiple Times

**Problem:**

````markdown
## Execution Process

### Step 1: Analyze Project

Run backend tests:

```bash
pytest tests/
pytest --cov
```
````

Run frontend tests:

```bash
npm test
npm test -- --coverage
```

## Backend Testing

Commands:

```bash
pytest tests/           # Same as above!
pytest --cov            # Duplicate!
```

## Frontend Testing

Commands:

```bash
npm test                # Same as above!
npm test -- --coverage  # Duplicate!
```

````

**Impact:** Commands repeated 2-3 times in single file

### ✅ Best Practice: Single Command Reference

```markdown
## Test Commands

**Backend:** `pytest tests/` | Coverage: `pytest --cov`
**Frontend:** `npm test` | Coverage: `npm test -- --coverage`

## Execution Process

1. **Run tests** using commands above
2. **Analyze failures** (see failure patterns below)
3. **Generate report**
````

**Savings:** 60% reduction, commands shown once

---

## 16. Framework-Specific Bloat in Generic Files

### ❌ Anti-Pattern: Including Irrelevant Framework Examples

**Problem (api-design.md for Next.js project):**

````markdown
## Flask API Patterns

### Flask-RESTX Models

```python
from flask_restx import Namespace, fields

api = Namespace('users')
user_model = api.model('User', {
    'id': fields.Integer,
    'email': fields.String
})
... [80 lines of Flask examples]
```
````

**Impact:** 80+ lines for framework not used in project

### ✅ Best Practice: Project-Relevant Examples Only

````markdown
## API Patterns

**For this project (Next.js API Routes):**

```typescript
// app/api/users/route.ts
export async function GET() {
    const users = await db.users.findMany();
    return Response.json(users);
}
```
````

**For other frameworks:** See framework-specific patterns in tech_stack.md

````

**Savings:** 85% reduction, keep only relevant examples

---

## 17. Over-Detailed Specification Examples

### ❌ Anti-Pattern: 200+ Line Example in Workflow

**Problem:**
```markdown
## Example Specification

# Technical Specification: Data Analysis Feature

## 1. Overview
[Full project context - 20 lines]

## 2. Architecture
[Complete system diagram - 30 lines]

## 3. API Design
### REST Endpoints
[15 endpoints with full schemas - 60 lines]

### GraphQL API
[10 queries, 5 mutations - 50 lines]

## 4. Database Schema
[MongoDB schemas for 8 collections - 40 lines]

## 5. File Structure
[Complete directory tree - 25 lines]

... [continues for 225 total lines]
````

**Impact:** 2.8x longer than prompt guidance (225 vs 80 lines)

### ✅ Best Practice: Minimal Illustrative Example

```markdown
## Example Specification (Abbreviated)

# Technical Specification: [Feature]

## Overview

Brief description, goals, scope

## API Design
```

POST /api/users
GET /api/users/:id

```

## Database
```

users: { id, email, name }
sessions: { id, userId, token }

```

**Note:** Real specs should be comprehensive. This example shows structure, not completeness.
```

**Savings:** 70% reduction (225 → ~70 lines), focus on structure not detail

---

## 18. Meta-Instruction Inflation in Commands

### ❌ Anti-Pattern: 3 Overlapping Validation Checklists

**Problem in command prompts:**

```markdown
## Quality Checklist

-   [ ] YAML frontmatter correct
-   [ ] No placeholders remain
-   [ ] Line count appropriate
-   [ ] Grammar perfect
        ... [11 items]

## Common Mistakes to Avoid

1. ❌ Missing YAML frontmatter
2. ❌ Using placeholders
3. ❌ Wrong line count
4. ❌ Grammar errors
   ... [6 items - 70% duplicate]

## Validation

-   [ ] Verify YAML frontmatter
-   [ ] Check no placeholders
-   [ ] Validate line count
-   [ ] Confirm grammar
        ... [8 items - 80% duplicate]
```

**Impact:** 25+ lines checking same things 3 times

### ✅ Best Practice: Single Consolidated Checklist

```markdown
## Quality Checklist

**Structure:**

-   [ ] YAML frontmatter correct
-   [ ] All required sections present

**Content:**

-   [ ] No placeholders remain
-   [ ] References valid guides/workflows
-   [ ] Examples concise (not verbose)

**Quality:**

-   [ ] Line count within target
-   [ ] Grammar perfect
```

**Savings:** 70% reduction (25 → 8 lines)

---

## 19. Placeholder Status Disclaimers

### ❌ Anti-Pattern: Temporary Status Messages in Final Documentation

**Problem (all file types - guides, workflows, agents):**

```markdown
## Current Status

**IMPORTANT:** No test framework configured yet. This guide describes recommended setup for future implementation.

**Recommended Frameworks:**
- **Backend (Python/Flask):** pytest...

## Running Tests

**Note**: Test framework not yet configured. When set up, use:

```bash
pytest  # Run all tests
```
```

**Why it's wrong:**
1. Memory Bank files are **final documentation**, not temporary drafts
2. These disclaimers remain **after features are implemented**, creating confusion
3. Makes agents **uncertain** about project state ("Does this exist or not?")
4. Breaks the "single source of truth" principle - file contradicts itself

**Impact:** Agent confusion, outdated documentation after first implementation, lack of clarity

### ✅ Best Practice: Assume Configuration, Provide Clear Instructions

**Instead of disclaimers, provide definitive instructions:**

```markdown
## Testing Frameworks

**Backend (Python/Flask):** pytest, pytest-cov, pytest-asyncio
**Frontend (Next.js/React):** Jest, React Testing Library, Playwright

Install dependencies:
```bash
# Backend
pip install pytest pytest-cov pytest-asyncio

# Frontend
npm install -D jest @testing-library/react playwright
```

## Running Tests

**Backend:**
```bash
pytest                    # Run all tests
pytest --cov             # With coverage
pytest tests/test_api.py # Specific file
```

**Frontend:**
```bash
npm test                 # Run all tests
npm test -- --coverage   # With coverage
```
```

**Why this works:**
- No temporal disclaimers ("not yet", "when configured", "in the future")
- Clear installation instructions at the top
- If command fails, agent sees clear error (`pytest: command not found`) and knows to install
- Works for projects **with OR without** tests already implemented
- Remains accurate after first tests are added - no manual updates needed

### Phrases to NEVER Generate

❌ "Not configured yet"
❌ "When set up..."
❌ "Future implementation"
❌ "Current status: missing"
❌ "To be implemented"
❌ "Placeholder for..."
❌ "Will be used when..."
❌ "[Technology] not detected"

### Instead: Assume Best-Case Setup

✅ Show installation commands first
✅ Provide run commands as if installed
✅ Let errors speak for themselves (agent will understand)
✅ Keep instructions concise and action-oriented

**Savings:** Removes 5-15 lines of disclaimers, improves clarity by 100%

---

## 20. Workflow-Guide Confusion

### ❌ Anti-Pattern: Workflows Embed Guide Content

**Problem (workflow prompts):**

```markdown
## Testing Workflow

### AAA Pattern Explanation
Arrange-Act-Assert is a testing pattern where you:
1. **Arrange**: Set up test data and preconditions
2. **Act**: Execute the code under test
3. **Assert**: Verify the results

**Example:**
```python
def test_user_creation():
    # Arrange
    user_data = {"email": "test@example.com"}
    # Act
    user = create_user(user_data)
    # Assert
    assert user.email == "test@example.com"
```

### Debugging Failing Tests
When a test fails:
1. Read the error message carefully
2. Check the assertion line...
[30+ more lines of testing guide content]
```

**Why it's wrong:**
1. **Workflows describe PROCESS** (when to test, what steps), not HOW-TO (test patterns, debugging)
2. **Guides contain DETAILS** (testing patterns, code examples, troubleshooting)
3. Duplicates testing guide content in workflow file (violates reference-first)
4. Makes workflows 300+ lines instead of 60 lines

**Impact:**
- testing-workflow.md: 59 lines (reference) → 388 lines (embedded guide content)
- code-review-workflow.md: 63 lines (reference) → 285 lines (embedded checklists)

### ✅ Best Practice: Workflows Reference Guides

```markdown
## Testing Workflow

### Step 1: Local Development Testing

As you develop, run tests relevant to your changes.

1. **Run Backend Tests**:
   - While working on backend, run pytest to validate changes
   - *Reference*: See [Backend Testing Commands](../guides/testing.md#backend-testing) for patterns

2. **Run Frontend Tests**:
   - While working on frontend, run vitest --watch for immediate feedback
   - *Reference*: See [Frontend Testing Commands](../guides/testing.md#frontend-testing)

### Step 2: Pre-PR Quality Gate

Before creating a PR, run full suite of local checks:
- Run all backend tests with coverage
- Run all frontend tests, linter, build
- *Reference*: See [Coverage Reports](../guides/testing.md#coverage-reports) and [E2E Testing](../guides/testing.md#e2e-testing)
```

**Why this works:**
- Workflow describes the SEQUENCE (Step 1 → Step 2 → Step 3 → Step 4)
- Guides provide the DETAILS (how to write tests, AAA pattern, debugging)
- No duplication - testing.md is single source of truth
- Workflow stays focused at 55-65 lines

**Rule:** If content belongs in a guide, **reference it**, don't **embed it**

**Savings:** 70-80% reduction in workflow file sizes

---

## 21. Completeness Bloat

### ❌ Anti-Pattern: "Self-Contained" Over "Reference-First"

**Problem (all workflow/guide prompts):**

Prompts following "Completeness Over Clarity" philosophy try to make each document "self-contained" by embedding all related information:

```markdown
# From generate-tasks.md.prompt (OLD VERSION)

## Task Breakdown Guidelines
**Granularity:**
- Each task: 0.5-3 days work
- Each subtask: 0.5-4 hours work

## Effort Estimation
**Simple**: 2-4 hours (basic CRUD)
**Medium**: 4-8 hours (complex logic)
[20+ lines of estimation formulas]

## Dependency Management
**Types**: Prerequisite, Blocking, Soft
[30+ lines explaining dependencies]

## Quality Checks
[15-item checklist]

## Troubleshooting
[20+ lines of common issues]

# Result: 443 lines instead of 100
```

**Why it's wrong:**
1. Tries to answer "what if user needs X?" by **embedding** instead of **referencing**
2. Creates 15-section workflows instead of focused 6-section workflows
3. Duplicates content across multiple files (estimation guide AND workflow AND command)
4. Generates 400+ line workflows when 100 lines would suffice

**Impact:** 7/7 workflow prompts showed 200-400% bloat

### ✅ Best Practice: Focus on Purpose, Reference Details

```markdown
# From generate-tasks.md.prompt (FIXED VERSION)

## Two-Phase Generation Process

### Phase 1: Generate Parent Tasks
AI generates high-level parent tasks with:
- Task number and title
- Brief description (1-2 sentences)
- Estimated effort
- Dependencies

**Example Phase 1 Output:**
[~40 line example showing structure]

**Does this look correct? Type "Go" to proceed.**

### Phase 2: Generate Detailed Sub-tasks
After user confirms, expand each parent task with:
- Detailed sub-task checklist
- Acceptance criteria

For task format details, see [Task Management Guide](../guides/task-management-guide.md).

# Result: 100 lines, focused on PROCESS, not HOW-TO
```

**Why this works:**
- Document has ONE purpose: describe two-phase workflow
- References task-management-guide.md for format details
- No duplication - each file owns its domain
- Clear separation: workflows = PROCESS, guides = HOW-TO

**Rule:** Before adding a section, ask: "Does this belong HERE or should I reference another file?"

**Savings:** 60-70% reduction, clearer document structure

---

## 22. Lost Interaction Models

### ❌ Anti-Pattern: Critical User Interaction Patterns Disappear

**Problem (workflow prompts generating interaction-based workflows):**

Original (reference project):
```markdown
### Phase 1: Generate Parent Tasks
[Generate task structure]

**Type "Go" to proceed with detailed sub-task generation.**

### Phase 2: Generate Detailed Sub-tasks
After user confirms with "Go", expand tasks...
```

Generated (target project):
```markdown
### Task Generation Process
1. Read PRD file
2. Analyze requirements
3. Break into tasks and subtasks
4. Generate tasks list file
5. Save to tasks/ directory

# Missing: User confirmation between phases
# Result: Autonomous generation, no user control
```

**Why it's wrong:**
1. **Lost user control**: Workflow becomes autonomous instead of interactive
2. **Missing confirmation**: "Type 'Go'" pattern disappears
3. **No permission model**: "One sub-task at a time with permission" becomes batch processing
4. **Wrong behavior**: Agent implements all sub-tasks without asking between each one

**Impact:**
- generate-tasks: Lost "Phase 1 → 'Go' → Phase 2" confirmation
- process-tasks-list: Lost "one sub-task → permission → next sub-task"
- Agent orchestration: Lost "suggest and wait for confirmation" for test-runner

### ✅ Best Practice: Preserve Interaction Patterns with Explicit Instructions

**In prompts, use CRITICAL annotations:**

```markdown
## Context

**CRITICAL INTERACTION MODEL**: This is NOT a one-shot generation.
The AI generates parent tasks (Phase 1), waits for user confirmation
with "Go", then generates sub-tasks (Phase 2).

## Output Requirements

### Phase 1: Generate Parent Tasks
[...]
**Does this structure look correct? Type "Go" to proceed.**

**CRITICAL**: The AI must ASK FOR CONFIRMATION before Phase 2.

### Phase 2: Generate Detailed Sub-tasks
After user types "Go" (or "Yes", "Continue", "Proceed"):
[...]
```

**In validation checklists:**
```markdown
- [ ] Phase 1 ends with "Type 'Go' to proceed" confirmation request
- [ ] Phase 2 describes what happens after "Go"
- [ ] User confirmation options listed (Go/Yes/Continue)
```

**Why this works:**
- CRITICAL annotations prevent LLM from treating pattern as "nice to have"
- Explicit validation items force pattern inclusion
- Multiple mentions reinforce importance

**Rule:** If workflow depends on user interaction, annotate with **CRITICAL** and validate explicitly

**Savings:** Preserves critical UX patterns, prevents automation creep

---

## 23. Hardcoded Tech in Prompts

### ❌ Anti-Pattern: Technology Examples in Project-Agnostic Prompts

**Problem (workflow/guide prompts):**

```markdown
## Example Specification

### Technologies
- Backend: Django / FastAPI
- Database: PostgreSQL
- Password Hashing: bcrypt
- Authentication: JWT tokens

### Code Example
```python
import bcrypt

def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        password.encode('utf-8'),
        bcrypt.gensalt()
    ).decode('utf-8')
```
```

**Why it's wrong:**
1. **Prompts are project-agnostic** - they generate for ANY project
2. **Hardcoded tech** creates bias: LLM suggests Django even for Express.js projects
3. **Generated files show wrong stack**: Flask project gets "Django / FastAPI" in docs
4. **Not using project-analysis.json**: Variables available but unused

**Impact:**
- create-spec.md.prompt: Django/PostgreSQL/bcrypt/JWT hardcoded
- create-prd.md.prompt: bcrypt/JWT hardcoded
- All projects get same tech examples regardless of actual stack

### ✅ Best Practice: Use Variables or Generic Patterns

**Option 1: Use {variables} from project-analysis.json:**

```markdown
## Example Specification

### Technologies
- Backend: {backend_framework}
- Database: {database}
- Additional Libraries: [List specific to feature]

## File Structure
```
{backend_dir}/
  [feature-module]/
    service.py
    models.py
```
```

**Option 2: Use generic descriptions:**

```markdown
## Technical Considerations
- Use industry-standard password hashing algorithm
- Session tokens should have appropriate expiration
- Integrate with existing database schema
```

**Why this works:**
- At **generation time**: {variables} filled from project-analysis.json
- In **generated file**: Shows actual project tech (Flask, MySQL, etc.)
- **Generic descriptions**: Work for any tech stack without bias

**Rule:** Prompts describe PATTERNS, not TECHNOLOGIES. Use {variables} or generic terms.

**Examples of fixes:**
```markdown
❌ "Use bcrypt for password hashing"
✅ "Use {auth_method} for password hashing" OR "Use industry-standard hashing"

❌ "Backend: Django / FastAPI"
✅ "Backend: {backend_framework}"

❌ import bcrypt
✅ import [hashing_library]  # Generic pseudo-code
```

**Savings:** Makes prompts truly project-agnostic, correct tech in all generated files

---

## 24. Self-Contained Over Reference-First

### ❌ Anti-Pattern: Documents Try to Be Complete Instead of Connected

**Problem (entire Memory Bank generation):**

**Philosophy conflict:**
- ❌ **"Completeness"**: Each document should contain all information reader needs
- ✅ **"Reference-First"**: Each document owns one domain, references others for details

**Example (testing-workflow.md trying to be "complete"):**

```markdown
# Testing Workflow (BLOATED VERSION - 388 lines)

## AAA Pattern
[50 lines explaining Arrange-Act-Assert]

## Writing Good Tests
[40 lines on test characteristics]

## Test Maintenance
[30 lines on refactoring tests]

## Debugging Failing Tests
[40 lines on troubleshooting]

## TDD Workflow
[50 lines on Red-Green-Refactor]

## Coverage Goals
[30 lines on coverage priorities]

# Result: Duplicates testing.md guide content
```

**Why it's wrong:**
1. **Document doesn't know its purpose**: Is it PROCESS (workflow) or HOW-TO (guide)?
2. **Duplication**: AAA pattern explained in testing.md AND testing-workflow.md
3. **Maintenance nightmare**: Update AAA pattern in 2 places when pattern changes
4. **Violates Single Source of Truth**: Two sources conflict

**Impact:** Average workflow 300+ lines instead of 60-120 lines

### ✅ Best Practice: Each Document Owns One Domain, References Others

**Reference-First Architecture:**

```markdown
# Testing Workflow (FOCUSED VERSION - 59 lines)

## 1. Purpose
This document outlines the standard workflow for testing features and bugfixes.
It defines the sequence of steps every developer must follow.

For detailed commands, code patterns, and troubleshooting, refer to the
[Testing Guide](../guides/testing.md), which is the single source of truth
for all technical testing details.

## 2. The Standard Testing Workflow

### Step 1: Local Development Testing
As you develop, run tests relevant to your changes:
- *Reference*: See [Backend Testing Commands](../guides/testing.md#backend-testing)

### Step 2: Pre-PR Quality Gate
Before creating PR, run full local checks:
- *Reference*: See [Coverage Reports](../guides/testing.md#coverage-reports)

### Step 3: CI Validation
After PR created, CI runs automatically

### Step 4: Verification & Merge
After code review and CI, ready to merge

## 3. Related Documentation
- [Testing Guide](../guides/testing.md) (The SSOT for commands/patterns)
- [Code Review Workflow](./code-review-workflow.md)
```

**Document Ownership Model:**

| Document Type | Owns | References |
|--------------|------|------------|
| **Workflows** | PROCESS (when, what steps, what order) | Guides for HOW-TO |
| **Guides** | HOW-TO (commands, patterns, examples) | Workflows for WHEN |
| **Agents** | VIOLATIONS (what to check, severity) | Guides for CORRECT patterns |
| **Commands** | ORCHESTRATION (what to invoke, order) | Workflows for PROCESS |

**Why this works:**
- Each document has ONE job
- No duplication - one source of truth per concept
- Updates in one place propagate via references
- Clear navigation: workflow → guide → agent

**Rule:** Before writing content, ask: "Do I OWN this content or should I REFERENCE it?"

**Checklist for prompts:**
```markdown
- [ ] Document purpose clearly stated (PROCESS vs HOW-TO vs VIOLATIONS)
- [ ] Content matches purpose (not mixing workflow + guide content)
- [ ] References to other docs for non-owned content
- [ ] No duplication of concepts explained elsewhere
```

**Savings:** 50-70% reduction, eliminates duplication across Memory Bank

---

## 25. Descriptive Workflows Instead of Prescriptive Rules

### ❌ Anti-Pattern: Workflows Explain Instead of Instruct

**Problem (workflow generation):**
Prompts generate workflows that DESCRIBE the process ("This workflow describes...", "The AI follows...") instead of PRESCRIBING actions ("The AI must...", "Step 1: Do X").

**Example:**
```markdown
# ❌ DESCRIPTIVE (example project generate-tasks.md):
# Generate Tasks Workflow

## Purpose
This workflow describes the AI process for converting a PRD into an actionable task list...

## Two-Phase Generation Process
The task generation follows a two-phase confirmation workflow:

### Phase 1: Generate Parent Tasks
The AI reads the PRD and generates HIGH-LEVEL parent tasks only:

**Parent Task Structure:**
- Task number and title
- Brief description (1-2 sentences)
...

**Example Phase 1 Output:** (35 lines of sample output)
```

**Why it's bad:**
- Explains WHAT the workflow is, not HOW to execute
- Long examples instead of exact templates
- Advice sections ("PRD Requirements", "After Generation")
- 138 lines for what should be 60 lines

**Fix:**
```markdown
# ✅ PRESCRIPTIVE (standard format):
# Rule: Generating a Task List from a PRD

## Goal
To guide an AI assistant in creating a detailed, step-by-step task list in Markdown format based on an existing PRD.

## Output
- **Format:** Markdown (`.md`)
- **Location:** `.memory_bank/tasks/[feature-name]/`
- **Filename:** `plan-[prd-file-name].md`

## Process
1. **Receive PRD Reference:** User points to PRD file
2. **Analyze PRD:** Read requirements and user stories
3. **Phase 1: Generate Parent Tasks:** Create main tasks, inform user
4. **Wait for Confirmation:** Pause for "Go"
5. **Phase 2: Generate Sub-Tasks:** Break down each parent task
6. **Identify Relevant Files:** List files to create/modify
7. **Generate Final Output:** Combine into format
8. **Save Task List:** Write to `.memory_bank/tasks/`

## Output Format
The generated task list _must_ follow this structure:

```markdown
## Relevant Files
- `path/file.ts` - Description

## Tasks
- [ ] 1.0 Parent Task
    - [ ] 1.1 Sub-task
```

## Interaction Model
Process requires pause after parent tasks to get user confirmation ("Go") before sub-tasks.

## Target Audience
Assume reader is a **junior developer** implementing the feature.
```

**Why it's better:**
- Title: "Rule:" (this is a rulebook)
- Goal: ONE sentence stating outcome
- Output: Concrete specs (format, location, naming)
- Process: NUMBERED actions (1-8)
- Output Format: EXACT template to produce
- 60 lines, all concrete rules

**Impact:**
- Example: 138 lines → should be ~60 lines (130% bloat)
- All 7 workflow prompts have this issue
- Generated files are explanatory, not instructive

**Root cause:**
Prompts instruct:
```markdown
#### 1. Header & Purpose
This workflow describes the AI process...

#### 2. Two-Phase Generation Process
describe the two-phase workflow...
```

Should instruct:
```markdown
#### 1. Header & Goal
# Rule: [Action from User Perspective]
## Goal
To guide AI in [concrete outcome]

#### 2. Output
Concrete specifications (format, location, naming)

#### 3. Process
NUMBERED steps, each an ACTION
```

**Fix in prompts:**
1. **Section names:** "Purpose" → "Goal", "Two-Phase Process" → "Process"
2. **Title format:** "Rule: [Action]" not "Workflow"
3. **Content type:** Templates and actions, not examples and explanations
4. **Remove advice sections:** "PRD Requirements", "After Generation", "Related Docs"
5. **Prescriptive language:** "The AI must..." not "The workflow describes..."

**Rule:** Workflows are RULEBOOKS (what to produce, how to execute), not EXPLANATIONS (what it is, why it works).

**Checklist for workflow prompts:**
```markdown
- [ ] Title format: "Rule: [Action]" (e.g., "Rule: Generating a Task List")
- [ ] Goal section: ONE sentence stating what AI achieves
- [ ] Output section: Format, Location, Filename specified
- [ ] Process section: NUMBERED steps (each an action)
- [ ] Output Format section: EXACT template in code block
- [ ] Interaction Model section: ONE paragraph (if relevant)
- [ ] 5-6 sections total (Goal, Output, Process, Output Format, ...)
- [ ] NO "Purpose" or "[Concept] Process" descriptive sections
- [ ] NO 30+ line examples showing sample output
- [ ] NO advice sections ("Requirements", "After Generation", "Related Docs")
- [ ] Prescriptive language throughout ("must", "step 1", not "describes")
- [ ] 50-70 lines target (concise rulebook)
```

**Detection:**
- "This workflow describes..." → Descriptive, not prescriptive
- "The AI follows..." → Descriptive
- Section "Two-Phase Generation Process" → Conceptual, not action-based
- 30+ line examples → Template should be 10-15 lines
- "PRD Requirements" or "After Generation" sections → Advice, not rules

**Savings:** 50% reduction (130 lines → 65 lines), workflows become actionable rulebooks

---

## Anti-Pattern Detection Checklist (Updated)

When reviewing generated files or prompts, check for:

-   [ ] Template repetition: Same structure shown 2+ times?
-   [ ] Code examples: More than 2 similar examples?
-   [ ] Checklists: Multiple checklists with overlapping items?
-   [ ] Concept re-explanation: Same concept explained 2+ times?
-   [ ] Verbose boilerplate: Static "What is X?" sections?
-   [ ] Example diversity: 5+ examples with similar structure?
-   [ ] Over-explanation: Obvious commands explained verbosely?
-   [ ] Structure duplication: Directory tree shown 2+ times?
-   [ ] Before/After pairs: More than 2 pairs for same concept?
-   [ ] Framework explanations: Explaining well-known technologies?
-   [ ] Troubleshooting redundancy: Restating best practices as solutions?
-   [ ] Severity definitions: Defined locally vs template variable?
-   [ ] **Inline documentation:** Agent duplicates guides instead of referencing?
-   [ ] **Report template bloat:** 60+ line format template in agent?
-   [ ] **Command duplication:** Same commands shown 2+ times in file?
-   [ ] **Framework bloat:** Examples for frameworks not used in project?
-   [ ] **Over-detailed examples:** Workflow examples 2-3x longer than guidance?
-   [ ] **Meta-instruction inflation:** 3+ overlapping validation checklists in prompt?
-   [ ] **Placeholder disclaimers:** "Not configured yet", "when set up", "future implementation"?
-   [ ] **Workflow-guide confusion:** Workflow embeds guide content instead of referencing?
-   [ ] **Completeness bloat:** Document tries to be self-contained instead of reference-first?
-   [ ] **Lost interaction models:** User confirmation patterns missing ("Type 'Go'", "Ask permission")?
-   [ ] **Hardcoded tech in prompts:** Django/bcrypt/JWT in project-agnostic prompts?
-   [ ] **Self-contained philosophy:** Document owns multiple domains instead of one?
-   [ ] **Descriptive workflows:** Workflow explains instead of instructs ("describes", "follows", long examples)?

**Target:** Check all 25 items before approving content

---

## Optimization Targets by File Type

### Agents (design-reviewer, test-runner)

**Target reduction:** 40-60%
**Focus on:**

-   Replace inline documentation with Memory Bank references
-   Reduce report format templates to 10-15 lines
-   Remove duplicate command listings
-   Reference guides for patterns, use agent for violations only

### Commands (prime, code-review, run-tests, etc.)

**Target reduction:** 50-65% (prompts only, generated files optimal)
**Focus on:**

-   Consolidate 3 validation checklists into 1
-   Remove "show and tell" redundancy
-   Keep commands that reference workflows (already optimal)

### Patterns (api-design, etc.)

**Target reduction:** 45-55%
**Focus on:**

-   Remove framework-specific examples not used in project
-   Reduce pattern repetition (1 example, then variations)
-   Replace exhaustive examples with representative samples

### Workflows (create-prd, create-spec, etc.)

**Target reduction:** 45-60%
**Focus on:**

-   Reduce example specifications from 200+ to 70-80 lines
-   Use domain-neutral examples, not project-heavy
-   Show structure, not exhaustive detail

---

**Last Updated:** 2025-11-18 (v2.2)
**Source:** workflow-prompts-fix-plan.md + prompt-redundancy-analysis.md (41 files analyzed)
**Total Patterns:** 25 (12 general + 13 specialized)
**Latest Addition:** Anti-Pattern #25 - Descriptive Workflows Instead of Prescriptive Rules
