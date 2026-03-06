# Memento Marketplace — Developer Guide

Monorepo containing two Claude Code plugins. Each plugin has its own `.claude-plugin/plugin.json`, `pyproject.toml`, and test suite. Users install each independently from the marketplace.

## Structure

```
repo-root/
├── .claude-plugin/marketplace.json  # Lists both plugins
├── pyproject.toml                   # Dev-only: uv workspace root, pytest config
├── memento/                         # Plugin: memento (Memory Bank generator)
│   ├── .claude-plugin/plugin.json
│   ├── pyproject.toml
│   ├── CLAUDE.md                    # Plugin-specific dev guide
│   └── ...
└── memento-workflow/                # Plugin: memento-workflow (workflow engine)
    ├── .claude-plugin/plugin.json
    ├── .mcp.json
    ├── pyproject.toml
    ├── CLAUDE.md                    # Plugin-specific dev guide
    └── ...
```

## Development

### Running all tests

```bash
uv run --all-packages pytest
```

This installs all workspace member deps and runs tests from both `memento/tests/` and `memento-workflow/tests/`.

### Running plugin tests independently

```bash
uv run --package memento-workflow pytest memento-workflow/tests/
uv run --all-packages pytest memento/tests/  # needs memento-workflow for type loading
```

### After changing memento prompts or static files

```bash
cd memento
python skills/analyze-local-changes/scripts/analyze.py recompute-source-hashes --plugin-root .
cd .. && uv run --all-packages pytest
```

## Plugins

- **memento**: AI-powered development environment generator with Memory Bank. See `memento/CLAUDE.md`.
- **memento-workflow**: Stateful workflow engine MCP server. See `memento-workflow/CLAUDE.md`.

The memento plugin depends on memento-workflow for its workflow commands (`create-environment`, `update-environment`).
