# Data Integrity Review

## Scope

Database safety, migrations, transactions, constraints, referential integrity, privacy.

Data loss is irreversible. Every migration, constraint change, or deletion path must be reviewed with this in mind.

## Rules

### Migrations

- Reversible: every migration has a rollback path (or explicit justification for irreversibility)
- No data loss: column drops, type changes, and renames preserve existing data
- NULL handling: new NOT NULL columns need defaults or backfill strategy
- Large tables: consider batched operations, lock impact, and deployment timing
- Idempotent when possible: re-running migration doesn't corrupt data
- Test with production-like data volume, not empty tables

### Constraints

- NOT NULL on fields that must always have values (don't rely on app-level validation alone)
- UNIQUE constraints at database level for fields that must be unique (not just app-level checks)
- Foreign keys defined for all relationships (orphaned records are data corruption)
- CHECK constraints for enums and bounded values when database supports them
- Validate both at database and application level — database is last defense

### Transactions

- Operations that must succeed or fail together wrapped in a transaction
- Transaction scope minimized — don't hold transactions open during external calls
- Isolation level appropriate (default is usually fine; document when stronger is needed)
- Deadlock risk assessed for transactions touching multiple tables in different orders
- Error handling rolls back properly — no partial state on failure

### Referential Integrity

- CASCADE vs RESTRICT on foreign keys is intentional, not default
- Deletion of parent records: verify child handling (cascade, nullify, restrict, or soft-delete)
- Soft deletes: queries filter deleted records consistently, foreign keys still work
- Polymorphic associations: referential integrity verified at application level

### Data Handling

- Sensitive data (PII) identified and protected: encryption at rest, restricted access
- Data retention: old data has cleanup/archival strategy
- Audit trail for critical data changes (who changed what, when)
- Bulk operations: verify rollback path if interrupted midway

### Edge Cases

- Empty strings vs NULL: consistent handling throughout the codebase
- Timezone handling: dates stored as UTC, converted at display
- Unicode: fields accept full UTF-8 range (emoji, CJK, RTL)
- Numeric precision: money and percentages use decimal types, not float

## Anti-Patterns

| Anti-Pattern | Signal | Fix |
|---|---|---|
| App-only validation | Unique check in code, no DB constraint | Add UNIQUE index |
| Orphan creation | Delete parent without handling children | CASCADE or RESTRICT FK |
| Implicit NULL semantics | NULL means "not set" in one place, "deleted" in another | Document and standardize |
| Unguarded migration | `ALTER TABLE DROP COLUMN` without data backup | Add reversibility or backup step |
| Fire-and-forget bulk | Update 1M rows in one statement | Batch with progress tracking |

## Severity

- **[CRITICAL]**: Possible data loss, missing transaction on multi-step write, migration without rollback
- **[REQUIRED]**: Missing DB constraint (relying on app-only), orphan risk, no cascade strategy
- **[SUGGESTION]**: Audit logging, tighter isolation level, timezone standardization
