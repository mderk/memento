---
status: In Progress
---
# Protocol: Relay Token Optimization

**Status**: Draft
**Created**: 2026-03-20
**PRD**: [./prd.md](./prd.md)

## Context

The memento-workflow relay passes all action data through the LLM context window. Prompt text (10-50KB), JSON schemas, and completed summaries are sent inline in MCP tool responses. In parallel lanes, identical data is duplicated per lane. Inter-step data transfer also uses inline variable piping instead of file references, adding serialization overhead and causing a hang bug.

## Decision

Apply "pass the path, not the content" principle everywhere: externalize prompts, schemas, and inter-step data to artifact files. Fix the stdin hang bug. Add compact mode for completed summaries. Deduplicate parallel lane prompts.

All changes are backward-compatible: inline fields remain populated when artifacts directory is unavailable, file-based fields are additive.

## Rationale

**Why file-based externalization over other approaches:**

- **Alternative: thin client relay** — requires reimplementing Claude Code's permission system and interactive tools. Not feasible without platform changes.
- **Alternative: MCP streaming / chunking** — MCP transport layer is not under our control.
- **Alternative: compress inline payloads** — LLM can't decompress; doesn't reduce context window usage.

File-based delivery is the only approach that works within current constraints: the server writes files (already does for audit), the LLM reads them with the Read tool (already does for context_files). The pattern is proven — we're extending it to cover the remaining inline payloads.

## Consequences

### Positive

- ~50% token reduction on prompt actions (prompt not duplicated in MCP response + context)
- Linear→constant scaling for parallel lanes with shared prompts
- Constant-size completed summaries regardless of workflow step count
- No changes required to MCP transport or Claude Code platform
- Fully backward-compatible — inline mode still works when artifacts unavailable

### Negative

- Each prompt action requires an extra Read tool call — adds ~1-2s latency per LLM step
- Relay protocol documentation must be updated — agents using old protocol still work but don't benefit
- Schema-by-reference requires LLM to track which schemas it has already read — adds cognitive load to relay

## Progress

- [x] [Fix stdin hang and add artifact path references for inter-step data](./01-fix-stdin-hang-and-add-artifact-path-references-for-inter-st.md) <!-- id:01-fix-stdin-hang-and-add-artifact-path-references-for-inter-st --> — 1.5h est

- [x] [Externalize prompt text to file](./02-externalize-prompt-text-to-file.md) <!-- id:02-externalize-prompt-text-to-file --> — 1.5h est

- [x] [Add schema_file to PromptAction](./03-add-schema-file-to-promptaction.md) <!-- id:03-add-schema-file-to-promptaction --> — 1h est

- [x] [Compact completed summary](./04-compact-completed-summary.md) <!-- id:04-compact-completed-summary --> — 45m est

- [ ] [Update relay protocol and run integration test](./06-update-relay-protocol-and-run-integration-test.md) <!-- id:06-update-relay-protocol-and-run-integration-test --> — 1h est
