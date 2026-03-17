"""
Movement tools — let the LLM agent set strategic waypoints for drones.
"""

from __future__ import annotations

import mcp_server.context as context


@context.mcp.tool()
def move_to(drone_id: int, x: int, y: int) -> dict:
    """
    Set a strategic waypoint for a drone at the given grid coordinates.

    The drone will navigate there at its configured speed over subsequent
    simulation ticks via its autonomous FSM. It will NOT arrive instantly.

    Parameters
    ----------
    drone_id : int
        Unique ID of the drone to command.
    x, y : int
        Target column and row in the grid.

    Returns
    -------
    dict
        Drone snapshot with ``waypoint_set: true`` and ``target: [x, y]``,
        or ``{"error": "..."}`` if the drone is not found or the target
        cell is blocked.
    """
    return context.world.set_drone_waypoint(drone_id, x, y)
