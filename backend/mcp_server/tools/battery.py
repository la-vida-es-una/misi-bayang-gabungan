"""
Battery / emergency tools — recall drones and broadcast survivor alerts.
"""

from __future__ import annotations

import mcp_server.context as context


@context.mcp.tool()
def return_to_base(drone_id: int) -> dict:
    """
    Command a drone to return to the charging base.

    The drone's FSM state is set to RETURN and it will fly back at its
    configured speed over subsequent simulation ticks. Battery is recharged
    automatically when the drone arrives at base.

    Parameters
    ----------
    drone_id : int
        Unique ID of the drone to recall.

    Returns
    -------
    dict
        Updated drone snapshot, or ``{"error": "..."}`` if the drone
        does not exist.
    """
    return context.world.command_drone_return(drone_id)


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
