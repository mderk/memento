"""Minimal MCP server to test whether subagents can see parent's MCP tools.

Two tools:
- ping(caller) — records caller, returns pong
- get_callers() — returns all recorded callers
"""

from mcp.server.fastmcp import FastMCP

server = FastMCP("workflow-test")

_callers: list[str] = []


@server.tool()
def ping(caller: str) -> dict:
    """Record a caller and return pong. Use to test MCP visibility from subagents."""
    _callers.append(caller)
    return {"status": "pong", "caller": caller, "total_pings": len(_callers)}


@server.tool()
def get_callers() -> dict:
    """Return all callers who have pinged this server."""
    return {"callers": _callers, "count": len(_callers)}


if __name__ == "__main__":
    server.run(transport="stdio")
