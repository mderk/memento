# Reusable Template Blocks

This file contains standardized content blocks that are referenced across multiple prompts using template variable syntax `{{BLOCK_NAME}}`.

**Usage in prompts:**
```
Include: {{MEMORY_BANK_EXPLANATION}}
```

**Note:** The environment-generator agent will replace these variables with the actual content during generation.

---

## {{MEMORY_BANK_EXPLANATION}}

The Memory Bank is a structured knowledge repository that serves as the single source of truth for project documentation. It provides:

- **Persistent Context:** Documentation that persists across sessions
- **Organized Knowledge:** Structured into guides, workflows, patterns, and specifications
- **AI-Optimized:** Designed for easy consumption by AI assistants
- **Living Documentation:** Kept synchronized with code evolution

**Structure:**
- **Guides:** Deep dives into specific topics (architecture, backend, frontend, testing)
- **Workflows:** Step-by-step processes for common development tasks
- **Patterns:** Reusable code and design patterns
- **Specs:** Feature specifications and technical design documents
- **Tasks:** Active and planned development work

---

## {{NAVIGATION_TIPS}}

**Navigation Tips:**

1. **Start with index files** - Each directory has an `index.md` that provides an overview
2. **Follow cross-references** - Documents link to related content for deep dives
3. **Use search** - Search for specific topics or patterns across all files
4. **Check task files** - See what's currently being worked on
5. **Review recent updates** - Check git history to find recently modified docs

---

## {{CONTRIBUTING_GUIDELINES}}

**Updating Memory Bank Files:**

1. **Keep documentation synchronized** with code changes
2. **Update cross-references** when renaming or moving files
3. **Follow established patterns** for consistency
4. **Add examples** from real project code when possible
5. **Link to external resources** for deeper technical details

---

## {{SEVERITY_LEVELS}}

**Severity Levels:**

- **[CRITICAL]** - Blocks PR merge, must fix immediately (security vulnerabilities, data loss risks)
- **[REQUIRED]** - Must fix before PR approval (bugs, broken functionality, poor practices)
- **[SUGGESTION]** - Improvement recommended but not blocking (optimization, refactoring, style)
- **[OPTIONAL]** - Nice to have, low priority (minor improvements, alternative approaches)

---

## {{STANDARD_CHECKLIST_STRUCTURE}}

**Checklist Format:**

Use consistent checkbox format for all checklists:
```markdown
- [ ] Item description (actionable, specific)
- [ ] Another item with context
```

**Categories:**
- Functional requirements
- Quality attributes
- Security considerations
- Performance requirements
- Documentation needs

---

## {{AAA_PATTERN_EXPLANATION}}

**AAA Testing Pattern:**

All tests should follow the Arrange-Act-Assert pattern:

1. **Arrange:** Set up test data and preconditions
2. **Act:** Execute the code being tested
3. **Assert:** Verify the expected outcome

This makes tests readable and maintainable by clearly separating setup, execution, and verification.

---

## {{COMMON_TEST_COMMANDS}}

**Running Tests:**

```bash
# Backend (pytest)
pytest path/to/tests/ -v

# Frontend (vitest/jest)
npm test path/to/tests/

# With coverage
pytest --cov=module_name
npm test -- --coverage

# Watch mode
pytest --watch
npm test -- --watch
```

---

## {{GIT_WORKFLOW_BASICS}}

**Git Workflow:**

```bash
# Create feature branch
git checkout -b feature/description

# Commit changes
git add .
git commit -m "description"

# Push to remote
git push -u origin feature/description

# Create PR
gh pr create --title "Title" --body "Description"
```

---

## {{PR_TEMPLATE_BASIC}}

**PR Description Template:**

```markdown
## Summary
[Brief description of changes]

## Changes
- Change 1
- Change 2

## Testing
- [ ] Tests added/updated
- [ ] Manual testing completed

## Related
Closes #issue-number
```

---

## {{ACCESSIBILITY_BASICS}}

**Accessibility Requirements (WCAG 2.1 AA):**

- **Keyboard Navigation:** All interactive elements accessible via keyboard
- **Screen Readers:** Proper ARIA labels and semantic HTML
- **Color Contrast:** Minimum 4.5:1 for normal text, 3:1 for large text
- **Focus Indicators:** Visible focus state for all interactive elements
- **Alt Text:** Descriptive text for all images

---

## {{SECURITY_CHECKLIST}}

**Security Checklist:**

- [ ] Input validation on all user inputs
- [ ] Output encoding to prevent XSS
- [ ] SQL injection prevention (parameterized queries)
- [ ] Authentication on protected endpoints
- [ ] Authorization checks for sensitive operations
- [ ] Secure password storage (bcrypt/argon2)
- [ ] HTTPS for all data transmission
- [ ] CSRF protection for state-changing operations
- [ ] Rate limiting on public endpoints
- [ ] Sensitive data not logged

---

## {{PERFORMANCE_BASICS}}

**Performance Considerations:**

- Database query optimization (avoid N+1 queries, use indexes)
- Caching strategies (Redis, in-memory)
- Lazy loading for large datasets
- Image optimization and lazy loading
- Code splitting for frontend bundles
- Pagination for large lists
- Debouncing/throttling for expensive operations

---

## {{ERROR_HANDLING_PATTERN}}

**Error Handling Pattern:**

```python
# Backend example
try:
    result = operation()
    return success_response(result)
except ValueError as e:
    logger.error(f"Validation error: {e}")
    return error_response("Invalid input", 400)
except Exception as e:
    logger.exception("Unexpected error")
    return error_response("Internal error", 500)
```

```typescript
// Frontend example
try {
  const result = await apiCall();
  return { success: true, data: result };
} catch (error) {
  console.error('Operation failed:', error);
  showToast('Error: ' + error.message, 'error');
  return { success: false, error };
}
```

---

## {{DOCUMENTATION_STANDARDS}}

**Documentation Standards:**

- **Code Comments:** Explain WHY, not WHAT (code should be self-documenting)
- **Docstrings:** All public functions/classes with parameters and return values
- **README files:** Setup instructions, architecture overview, contribution guidelines
- **Inline Documentation:** Complex algorithms, business logic, non-obvious decisions
- **API Documentation:** All endpoints with request/response examples

---

## {{CONDITIONAL_FRONTEND_CONTENT}}

**Conditional:** Only include when `has_frontend` is true

Content specific to frontend development (React/Vue/Angular patterns, component structure, state management, etc.)

---

## {{CONDITIONAL_BACKEND_CONTENT}}

**Conditional:** Only include when `has_backend` is true

Content specific to backend development (API design, database patterns, authentication, etc.)

---

## {{TROUBLESHOOTING_FORMAT}}

**Troubleshooting Format:**

Use Q&A format for common issues:

**Problem:** Clear description of the issue
**Cause:** Root cause explanation
**Solution:** Step-by-step fix
**Prevention:** How to avoid in future

---

## {{RELATED_DOCS_SECTION}}

**Related Documentation:**

- [Link to related guide](path)
- [Link to workflow](path)
- [Link to pattern](path)

Refer to these for deeper understanding of specific topics.

---

## Usage Examples in Prompts

### Example 1: Replacing static "What is Memory Bank?" section

**Before:**
```markdown
## What is the Memory Bank?

The Memory Bank is a structured knowledge repository that serves as the single source of truth for project documentation. It provides:
[... 20+ lines of boilerplate ...]
```

**After:**
```markdown
## What is the Memory Bank?

{{MEMORY_BANK_EXPLANATION}}
```

### Example 2: Consolidating navigation tips

**Before:**
```markdown
## Navigation Tips

1. Start with index files - Each directory has an index.md...
2. Follow cross-references - Documents link to...
[... repetitive in every file ...]
```

**After:**
```markdown
## Navigation Tips

{{NAVIGATION_TIPS}}
```

### Example 3: Reusing severity levels

**Before:**
- Severity levels explained in code-review-workflow.md
- Same explanation in code-review-guidelines.md
- Same explanation in bug-fix-workflow.md
- Same explanation in agent-orchestration.md

**After:**
- All four files reference: {{SEVERITY_LEVELS}}
- Maintained in one place

---

## Benefits

1. **Consistency:** Same content across all generated files
2. **Maintainability:** Update once, affects all files
3. **Reduced Redundancy:** 30-40% reduction in prompt size
4. **Clarity:** Prompts focus on unique content, not boilerplate
