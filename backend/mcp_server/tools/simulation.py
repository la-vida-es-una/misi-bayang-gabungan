"""
Simulation control tools — advance the world clock.
"""

from __future__ import annotations

import mcp_server.context as context


@context.mcp.tool()
def step(ticks: int = 1) -> dict:
    """
    Advance the simulation by the given number of ticks.

    This allows autonomous agents (drones, survivors) to perform their
    logic (movement, sensing, communication) for the specified duration.

    Parameters
    ----------
    ticks : int, default=1
        Number of simulation steps to run.

    Returns
    -------
    dict
        ``{"success": True, "new_tick": int}``
    """
    for _ in range(max(1, ticks)):
        context.world.step()

    return {
        "success": True,
        "new_tick": context.world.steps,
    }
