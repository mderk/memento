# Rule: Generating a Technical Specification

## Goal

Guide AI assistants in creating a detailed Technical Specification in Markdown format from a PRD, including architecture, data models, and implementation details.

## Output

-   **Format**: Markdown (`.md`)
-   **Location**: `.protocols/NNNN-feature-name/` (same directory as the PRD)
-   **Filename**: `spec.md`
-   **Sections**: 11 required sections (Overview through Open Questions)

## Process

1. **Locate Protocol**: User provides protocol number or directory path. Find `.protocols/NNNN-*/prd.md`
2. **Analyze PRD**: Read `prd.md` from the protocol directory — requirements, user stories, acceptance criteria
3. **Research Codebase**: Study existing architecture, patterns, components
4. **Ask Clarifying Questions**: Resolve ambiguities — tech stack choices, architecture approach, data model, API design, security requirements
5. **Generate Specification**: Create spec with 11 sections (see Output Format below)
6. **Save Specification**: Write to `.protocols/NNNN-feature-name/spec.md`

## Output Format

The generated specification _must_ include these 11 sections:

1. **Overview**: Technical summary (1-2 paragraphs)
2. **System Architecture & Design Patterns**: Patterns used (MVC, Service-Repository, etc.)
3. **Technologies, Frameworks, Libraries**: Project's detected stack plus any additional libraries needed
4. **File & Folder Structure**: Tree showing new/modified files
5. **Modules, Classes, Components**: Breakdown with responsibilities
6. **Public API / Endpoints**: REST/GraphQL endpoints, request/response formats
7. **Data Model / Schema**: Database schema changes
8. **External Services & Integrations**: Third-party integrations, configuration
9. **Configuration & Environment Variables**: New env vars needed
10. **Code Snippets**: Key implementation patterns (use sparingly)
11. **Open Questions**: Unresolved technical questions

## Related Documentation

-   [Create PRD Workflow](../create-prd/workflow.md)
-   [Create Protocol Workflow](../create-protocol/workflow.md)
-   `/develop` workflow
-   [Architecture Guide](../guides/architecture.md)
