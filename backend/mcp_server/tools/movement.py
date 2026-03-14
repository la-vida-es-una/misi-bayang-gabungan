"""
Movement tools — let the LLM agent reposition any drone on the grid.
"""

from __future__ import annotations

import mcp_server.context as context


@context.mcp.tool()
def move_to(drone_id: int, x: int, y: int) -> dict:
    """
    Move a drone to the given grid coordinates.

    Parameters
    ----------
    drone_id : int
        Unique ID of the drone to move.
    x, y : int
        Target column and row in the grid.

    Returns
    -------
    dict
        Updated drone snapshot, or ``{"error": "..."}`` if the drone is not
        found or the target cell is blocked.
    """
    return context.world.move_drone_to(drone_id, x, y)
