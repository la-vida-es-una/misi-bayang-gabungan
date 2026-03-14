"""
Sensor tools — thermal imaging and grid-map queries.
"""

from __future__ import annotations

from simulation import DroneAgent, SurvivorAgent

import mcp_server.context as context


@context.mcp.tool()
def thermal_scan(drone_id: int) -> dict:
    """
    Run a thermal scan from the drone's current position.

    Marks any survivors within the drone's ``vision_radius`` as FOUND.

    Parameters
    ----------
    drone_id : int
        Unique ID of the scanning drone.

    Returns
    -------
    dict
        ``{
            "drone_id": int,
            "detections": [...],   # list of survivor snapshots
            "survivor_detected": bool,
            "confidence": float    # heuristic: 0.95 when detected else 0.0
        }``
        or ``{"error": "..."}`` if the drone does not exist.
    """
    result = context.world.thermal_scan(drone_id)
    if "error" in result:
        return result

    detected = len(result["detections"]) > 0
    result["survivor_detected"] = detected
    result["confidence"] = 0.95 if detected else 0.0
    return result


@context.mcp.tool()
def get_grid_map() -> dict:
    """
    Return the current known grid map.

    Aggregates all cells visited by any active drone and the positions of
    all known (found/rescued) survivors.

    Returns
    -------
    dict
        ``{
            "scanned": [[x, y], ...],
            "survivors": [[x, y], ...]
        }``
    """
    visited: set[tuple[int, int]] = set()
    for agent in context.world.agents:  # type: ignore[attr-defined]
        if isinstance(agent, DroneAgent):
            visited.update(agent.visited_cells)

    survivors: list[list[int]] = []
    for agent in context.world.agents:  # type: ignore[attr-defined]
        if isinstance(agent, SurvivorAgent) and agent.state.value in ("found", "rescued"):
            sx, sy = agent._pos()
            survivors.append([sx, sy])

    return {
        "scanned": [list(cell) for cell in visited],
        "survivors": survivors,
    }
