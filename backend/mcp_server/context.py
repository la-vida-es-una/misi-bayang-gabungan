"""
Shared context for the MCP server.

This module holds the FastMCP application instance and the simulation world
singleton to avoid circular dependencies between the main server entry point
and the tool/resource modules.
"""

from __future__ import annotations

from fastmcp import FastMCP
from simulation import SARWorld

# ---------------------------------------------------------------------------
# Shared simulation singleton
# ---------------------------------------------------------------------------
world: SARWorld = SARWorld(
    n_drones=5,
    n_survivors=6,
    width=100,
    height=100,
    n_obstacles=6,
    vision_radius=8.0,
    comm_radius=18.0,
    battery_drain=0.9,
    low_battery=20.0,
    speed=1.0,
    seed=None,
)

# ---------------------------------------------------------------------------
# FastMCP app
# ---------------------------------------------------------------------------
mcp: FastMCP = FastMCP(
    name="Misi Bayang — SAR Drone Control",
    instructions=(
        "You control a swarm of search-and-rescue drones over a 100×100 grid. "
        "Use the tools to move drones, thermal-scan for survivors, and recall "
        "drones when their battery is low. Read mission://state for a full world "
        "snapshot at any time. Use simulation.step to advance the world clock."
    ),
)
