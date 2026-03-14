"""
Battery / emergency tools — recall drones and broadcast survivor alerts.
"""

from __future__ import annotations

import mcp_server.context as context


@context.mcp.tool()
def return_to_base(drone_id: int) -> dict:
    """
    Immediately recall a drone to the charging base and recharge it.

    The drone is teleported to ``world.base_pos``.  Its battery is reset to
    100 and its internal knowledge (known survivors, goals) is cleared, ready
    for the next deployment.

    Parameters
    ----------
    drone_id : int
        Unique ID of the drone to recall.

    Returns
    -------
    dict
        ``{"success": bool, "drone_id": int, "x": int, "y": int,
           "battery": float}``
        or ``{"error": "..."}`` if the drone does not exist.
    """
    drone = context.world.get_drone(drone_id)
    if drone is None:
        return {"error": f"drone {drone_id} not found"}

    bx, by = context.world.base_pos
    context.world.grid.move_agent(drone, (bx, by))
    drone.battery = 100.0
    drone.known_survivors = []
    drone.known_edges = set()
    drone._goal = None  # type: ignore[attr-defined]

    from simulation import DroneState
    drone.state = DroneState.EXPLORE

    return {
        "success": True,
        "drone_id": drone_id,
        "x": bx,
        "y": by,
        "battery": 100.0,
    }


@context.mcp.tool()
def broadcast_alert(x: int, y: int, message: str) -> dict:
    """
    Broadcast a survivor alert to all units at the given coordinates.

    This is a coordination primitive — the simulation records the alert in
    its log and all listening agents can act on it in subsequent ticks.

    Parameters
    ----------
    x, y : int
        Grid coordinates of the alert.
    message : str
        Human-readable alert description.

    Returns
    -------
    dict
        ``{"success": True, "x": int, "y": int, "message": str}``
    """
    # Log the alert to the simulation event log (stored in context.world metadata)
    if not hasattr(context.world, "_alerts"):
        context.world._alerts = []  # type: ignore[attr-defined]
    context.world._alerts.append({"x": x, "y": y, "message": message, "tick": context.world.steps})  # type: ignore[attr-defined]

    return {"success": True, "x": x, "y": y, "message": message}
