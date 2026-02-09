# Performance Review

## Scope

Algorithmic complexity, database queries, memory usage, caching, network efficiency.

Focus on changes that affect data paths at scale. Don't optimize what isn't a bottleneck.

## Rules

### Algorithmic Complexity

- No O(n^2) or worse without justification and a comment explaining why
- Nested loops over collections: verify the inner set is bounded
- String concatenation in loops: use builder/join pattern
- Sorting: don't sort when you can use a heap, set, or index

### Database

- No N+1 queries (loading related data inside a loop)
- Queries use appropriate indexes — new WHERE/ORDER BY columns need index analysis
- Large result sets paginated, not loaded entirely into memory
- Transactions scoped minimally — don't hold locks during I/O or computation
- Migrations on large tables: consider impact on lock time and running queries

### Memory

- No unbounded data structures (lists/dicts that grow with input without limits)
- Large files processed as streams, not loaded entirely
- Caches have eviction policy (TTL or LRU), not grow-forever
- Event listeners and subscriptions cleaned up on teardown

### Caching

- Cache invalidation strategy exists (not just "cache forever")
- Cache keys include all parameters that affect the result
- Cached data has TTL appropriate to its staleness tolerance
- No caching of user-specific data in shared caches without proper keying

### Network

- Batch API calls where possible (one request for N items, not N requests)
- Payload size reasonable — no sending entire objects when IDs suffice
- Compression enabled for large responses
- No synchronous external API calls in request hot path without timeout

### Frontend (if applicable)

- No large dependencies added for small features (check bundle size impact)
- Images/assets lazy-loaded or properly sized
- No layout thrashing (reading then writing DOM in loops)
- Expensive computations memoized or debounced

## Anti-Patterns

| Anti-Pattern | Signal | Fix |
|---|---|---|
| N+1 queries | Loop with ORM `.load()` or `.get()` inside | Eager load / batch query |
| Unbounded fetch | `SELECT * FROM logs` without LIMIT | Paginate or stream |
| Cache stampede | Cache expires, 100 requests rebuild simultaneously | Lock or stale-while-revalidate |
| Premature optimization | Caching data accessed once per hour | Remove cache, add when actually needed |
| Synchronous waterfall | `await a(); await b(); await c()` when independent | `Promise.all([a(), b(), c()])` |

## Severity

- **[CRITICAL]**: Unbounded query, missing pagination on large table, memory leak
- **[REQUIRED]**: N+1 query, missing index for frequent query, O(n^2) on user data
- **[SUGGESTION]**: Memoization opportunity, batch optimization, compression
