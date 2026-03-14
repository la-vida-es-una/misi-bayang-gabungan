"""
Mission state resource — exposes the full world snapshot via MCP resources.
"""

from __future__ import annotations

import mcp_server.context as context


@context.mcp.resource("mission://state")
def mission_state() -> dict:
    """
    Full simulation state snapshot.

    Returns
    -------
    dict
        ``{
            "tick": int,
            "drones": [...],
            "survivors": [...],
            "obstacles": [...],
            "coverage_pct": float,
            "base_pos": [x, y],
            "grid": {"width": int, "height": int},
            "mission_complete": bool
        }``
    """
    return context.world.get_state()
