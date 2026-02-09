# Security Review

## Scope

Vulnerabilities, authentication, authorization, data exposure, input handling.

Think like an attacker. Assume worst-case input for every external boundary.

## Rules

### Input Validation

- All user input validated at system boundary (API handlers, form processors, CLI args)
- Validation is allowlist-based (accept known good), not denylist (reject known bad)
- File uploads: validate type, size, name; never trust client-provided MIME type
- URLs/redirects: validate against allowlist of domains, reject open redirects

### Injection

- SQL: parameterized queries only, never string concatenation/interpolation
- XSS: output encoding by default, raw HTML rendering requires explicit justification
- Command injection: no user input in shell commands; if unavoidable, use allowlists and escaping
- Path traversal: canonicalize paths, reject `..` sequences, validate against base directory
- Template injection: no user input in template strings evaluated server-side

### Authentication & Authorization

- Auth checks on every endpoint, not just frontend guards
- Authorization checked at data layer, not just route level (verify ownership of the resource)
- Tokens/sessions have expiration
- Password hashing uses bcrypt/scrypt/argon2, never MD5/SHA
- No auth logic in client-side code that can be bypassed

### Secrets

- No hardcoded credentials, API keys, tokens in source code
- Secrets loaded from environment variables or secret managers
- `.env` files in `.gitignore`
- Error messages don't expose internal details (stack traces, SQL, file paths)
- Logs don't contain PII or secrets

### Data Exposure

- API responses return only necessary fields (no `SELECT *` leaking to client)
- Sensitive fields (password, SSN, tokens) never in API responses
- Debug/admin endpoints protected or disabled in production
- CORS configured to specific origins, not `*`

### Dependencies

- No known vulnerable dependencies (check CVEs)
- Dependencies pinned to specific versions
- New dependencies reviewed for maintenance status and security track record

## Anti-Patterns

| Anti-Pattern | Example | Fix |
|---|---|---|
| Trust the client | `if (user.isAdmin)` checked only in JS | Server-side auth check |
| Roll your own crypto | Custom token generation with `Math.random()` | Use established library |
| Verbose errors | `catch(e) { res.json({ error: e.stack })` | Generic error message, log details server-side |
| Overpermissioned endpoint | PATCH endpoint accepts `role` field | Allowlist mutable fields |
| Secret in URL | `?api_key=xxx` | Use headers |

## Severity

- **[CRITICAL]**: Injection vulnerability, missing auth, exposed secrets, open redirect
- **[REQUIRED]**: Insufficient input validation, verbose errors, missing CORS config
- **[SUGGESTION]**: Dependency version pinning, stricter CSP headers
