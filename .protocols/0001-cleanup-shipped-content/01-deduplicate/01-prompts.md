---
id: 01-deduplicate-01-prompts
status: done
estimate: 2h
---

# Deduplicate product_brief / tech_stack / architecture Prompts

## Objective

<!-- objective -->
Remove content overlap between the three core prompt templates so each file has a single clear responsibility:
- **product_brief**: what the project is (30–50 lines)
- **tech_stack**: dependencies, tools, versions, commands (120–180 lines)
- **architecture**: conceptual system design, data flow, decisions (250–350 lines)
<!-- /objective -->

## Tasks

<!-- tasks -->
- [ ] Edit `prompts/memory_bank/product_brief.md.prompt`:
  - Remove "Technology Stack" section (§2) — replace with link to tech_stack.md
  - Remove "Architecture" section (§3) — replace with link to architecture guide
  - Keep: Overview (verbatim project_description), Technical Constraints (optional), Development Resources (links)
  - Update target_lines to 30-50 (from 50)
  - Update example output to match new structure
- [ ] Edit `prompts/memory_bank/tech_stack.md.prompt`:
  - Remove sections: Infrastructure (§5), Security (§7), Performance (§8), Documentation (§9)
  - Keep: Overview, Backend, Frontend, Database subsections, Development Tools
  - Add cross-reference to architecture guide for system design context
  - Add cross-reference to backend/frontend guides for detailed directory structures
  - Reduce target_lines to 120-180 (from 200-300)
  - Simplify directory structure examples (3 levels max, details in backend/frontend guides)
- [ ] Edit `prompts/memory_bank/guides/architecture.md.prompt`:
  - Remove "Technology Stack Summary" table (§3) — replace with link to tech_stack.md
  - Remove or collapse sections 10-16 (Error Handling, Performance, Scalability, Security Architecture, Deployment Architecture, Future Considerations) — these are speculative/duplicated
  - Keep: System Overview + diagram, Component Architecture, Data Flow, API Design, Auth, Communication Patterns, Design Decisions, Diagrams, References
  - Reduce target_lines to 250-350 (from 400-600)
  - Ensure directory structures in Component Architecture are brief (link to tech_stack for full trees)
- [ ] Verify cross-references are consistent across all three prompts
- [ ] Update quality checklists in each prompt to reflect new scope
<!-- /tasks -->

## Constraints

<!-- constraints -->
- Each topic must exist in exactly ONE file (no duplication)
- Cross-references use relative paths (e.g., `[Tech Stack](../tech_stack.md)`)
- Prompt format must remain valid per `prompts/SCHEMA.md`
- Examples in prompts must be updated to match new structure
<!-- /constraints -->

## Implementation Notes

Key files to modify:
- `memento/prompts/memory_bank/product_brief.md.prompt`
- `memento/prompts/memory_bank/tech_stack.md.prompt`
- `memento/prompts/memory_bank/guides/architecture.md.prompt`

Content ownership after deduplication:

| Topic | Owner | Others link to |
|-------|-------|---------------|
| Project description | product_brief | — |
| Tech list + versions | tech_stack | product_brief, architecture |
| Directory structure (brief) | tech_stack | architecture |
| Directory structure (detailed) | backend/frontend guides | tech_stack |
| System design + diagrams | architecture | product_brief, tech_stack |
| API design | architecture | tech_stack (mentions api_style only) |
| Infrastructure/Deployment | tech_stack (minimal) | — |
| Security/Performance concepts | REMOVED (speculative) | — |

## Verification

<!-- verification -->
```bash
uv run python -c 'import yaml, pathlib; [print(f + ": OK") for f in ["memento/prompts/memory_bank/product_brief.md.prompt", "memento/prompts/memory_bank/tech_stack.md.prompt", "memento/prompts/memory_bank/guides/architecture.md.prompt"] if yaml.safe_load(pathlib.Path(f).read_text().split("---", 2)[1])]'
```
<!-- /verification -->

## Context

<!-- context:files -->
- memento/prompts/SCHEMA.md
- memento/prompts/anti-patterns.md
<!-- /context:files -->

## Starting Points

<!-- starting_points -->
- memento/prompts/memory_bank/product_brief.md.prompt
- memento/prompts/memory_bank/tech_stack.md.prompt
- memento/prompts/memory_bank/guides/architecture.md.prompt
<!-- /starting_points -->

## Findings

<!-- findings -->
<!-- /findings -->

## Memory Bank Impact

- [ ] None expected (changes are to prompts, not to memento's own Memory Bank)
