"""
mcp_server package.

Public exports:
    mcp   — the FastMCP application instance
    world — the shared SARWorld simulation singleton
"""

from mcp_server.context import mcp, world  # noqa: F401

__all__ = ["mcp", "world"]
