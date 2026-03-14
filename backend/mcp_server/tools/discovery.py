"""
Discovery tools — enumerate drones and inspect individual drone status.
"""

from __future__ import annotations

import mcp_server.context as context


@context.mcp.tool()
def list_active_drones() -> dict:
    """
    List all drones that still have battery remaining.

    Returns
    -------
    dict
        ``{"drones": [<drone_id>, ...]}``
        where each entry is the integer unique_id of an active drone.
    """
    active = context.world.list_active_drones()
    return {"drones": [d["id"] for d in active]}


@context.mcp.tool()
def get_drone_status(drone_id: int) -> dict:
    """
    Return the full status snapshot of a single drone.

    Parameters
    ----------
    drone_id : int
        Unique ID of the drone to inspect.

    Returns
    -------
    dict
        Full drone snapshot with keys: id, x, y, state, battery,
        visited_cells, known_survivors, known_edges, target_survivor.
        Returns ``{"error": "..."}`` if the drone is not found.
    """
    drone = context.world.get_drone(drone_id)
    if drone is None:
        return {"error": f"drone {drone_id} not found"}
    return drone.to_dict()
