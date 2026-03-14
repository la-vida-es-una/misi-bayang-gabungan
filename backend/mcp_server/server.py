"""
FastMCP server entry point for Misi Bayang Gabungan.

Starts a SAR (Search and Rescue) simulation world and exposes it through the
Model Context Protocol so that LLM agents can drive the swarm.

Usage (stdio transport — default for MCP clients):
    uv run python -m mcp_server.server

Usage (SSE transport — for browser / HTTP clients):
    uv run python -m mcp_server.server --transport sse --port 8765
"""

from __future__ import annotations

import argparse

from fastmcp import FastMCP

from simulation import SARWorld

# ---------------------------------------------------------------------------
# Shared simulation and MCP instances
# ---------------------------------------------------------------------------
from mcp_server.context import mcp, world

# ---------------------------------------------------------------------------
# Register tool and resource modules
# ---------------------------------------------------------------------------
import mcp_server.tools.movement   # noqa: E402, F401
import mcp_server.tools.sensors    # noqa: E402, F401
import mcp_server.tools.discovery  # noqa: E402, F401
import mcp_server.tools.battery    # noqa: E402, F401
import mcp_server.tools.simulation # noqa: E402, F401
import mcp_server.resources.mission_state  # noqa: E402, F401


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Misi Bayang MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="SSE host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="SSE port (default: 8765)",
    )
    args = parser.parse_args()

    if args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
