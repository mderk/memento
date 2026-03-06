# Memento Marketplace

A Claude Code plugin marketplace containing two plugins that work together to generate and automate AI-friendly development environments.

## Plugins

### [memento](memento/) — AI-Powered Development Environment

Generates Memory Bank documentation, specialized AI agents, and workflow automation for any project.

- **Memory Bank** — structured docs (guides/, workflows/, patterns/)
- **Specialized AI Agents** — test runner, developer, code reviewer, design reviewer
- **Workflow Automation** — PRD → Spec → Protocol → Implementation pipeline
- **Tech Stack Agnostic** — works with any backend/frontend/database combination

Commands: `/memento:create-environment`, `/memento:update-environment`, `/memento:import-knowledge`, `/memento:optimize-memory-bank`

See [memento/README.md](memento/README.md) for full documentation, installation, and quick start.

### [memento-workflow](memento-workflow/) — Workflow Engine

Stateful MCP server for multi-step workflow automation with checkpoint/resume, interactive prompts, and parallel execution.

- **9 block types** — shell, prompt, LLM, group, parallel, loop, retry, conditional, subworkflow
- **Durable checkpointing** — resume interrupted workflows
- **Relay protocol** — Claude Code drives execution via MCP tools

See [memento-workflow/CLAUDE.md](memento-workflow/CLAUDE.md) for architecture and development guide.

## Installation

```bash
# Add marketplace
/plugin marketplace add mderk/memento

# Install both plugins
/plugin install memento-marketplace@memento
/plugin install memento-marketplace@memento-workflow
```

## Development

See [CLAUDE.md](CLAUDE.md) for development setup and testing.

## License

MIT License — see [LICENSE](LICENSE) file.

## Links

- [GitHub Repository](https://github.com/mderk/memento)
- [Issues](https://github.com/mderk/memento/issues)
- [Claude Code Documentation](https://docs.anthropic.com/en/docs/claude-code)
