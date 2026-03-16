"""
LiveMCPClient — bridges MCPClientProtocol to a live SARWorld instance.

Translates string drone IDs ("drone_6") to Mesa integer IDs (6),
simulates battery drain on moves/scans, tracks visited cells for
coverage, and auto-rescues survivors found at the drone's position.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from .interfaces import DroneStatus, GridMap, MoveResult, ScanResult

if TYPE_CHECKING:
    from simulation.world import SARWorld

logger = logging.getLogger(__name__)

BATTERY_DRAIN_MOVE = 3
BATTERY_DRAIN_SCAN = 1


class LiveMCPClient:
    """
    Implements MCPClientProtocol by wrapping a live SARWorld instance.

    All MCP method calls translate directly to SARWorld operations,
    with added battery drain and coverage tracking that the raw
    world methods don't provide.
    """

    def __init__(self, world: "SARWorld") -> None:
        self._world = world

    # ── ID translation ───────────────────────────────────────────────

    @staticmethod
    def _to_int(drone_id: str) -> int:
        """'drone_6' -> 6"""
        return int(drone_id.split("_")[1])

    @staticmethod
    def _to_str(drone_id: int) -> str:
        """6 -> 'drone_6'"""
        return f"drone_{drone_id}"

    # ── MCPClientProtocol implementation ─────────────────────────────

    async def list_active_drones(self) -> dict[str, list[str]]:
        active = self._world.list_active_drones()
        return {"drones": [self._to_str(d["id"]) for d in active]}

    async def get_drone_status(self, drone_id: str) -> DroneStatus:
        did = self._to_int(drone_id)
        drone = self._world.get_drone(did)
        if drone is None:
            raise ValueError(f"Drone {drone_id} not found")
        x, y = drone._pos()
        return DroneStatus(
            drone_id=drone_id,
            battery=int(drone.battery),
            x=x,
            y=y,
            state=drone.state.value,
        )

    async def move_to(self, drone_id: str, x: int, y: int) -> MoveResult:
        did = self._to_int(drone_id)
        drone = self._world.get_drone(did)
        if drone is None:
            return MoveResult(success=False, drone_id=drone_id, x=x, y=y)

        # Drain battery
        drone.battery = max(0.0, drone.battery - BATTERY_DRAIN_MOVE)
        if drone.battery <= 0:
            return MoveResult(
                success=False, drone_id=drone_id, x=drone._pos()[0], y=drone._pos()[1]
            )

        result = self._world.move_drone_to(did, x, y)
        if "error" in result:
            return MoveResult(success=False, drone_id=drone_id, x=x, y=y)

        # Track visited cell for coverage
        drone.visited_cells.add((x, y))

        return MoveResult(success=True, drone_id=drone_id, x=x, y=y)

    async def thermal_scan(self, drone_id: str) -> ScanResult:
        did = self._to_int(drone_id)
        drone = self._world.get_drone(did)
        if drone is None:
            return ScanResult(survivor_detected=False, confidence=0.0, x=0, y=0)

        # Drain battery
        drone.battery = max(0.0, drone.battery - BATTERY_DRAIN_SCAN)

        dx, dy = drone._pos()
        result = self._world.thermal_scan(did)

        if "error" in result:
            return ScanResult(survivor_detected=False, confidence=0.0, x=dx, y=dy)

        detections = result.get("detections", [])
        if detections:
            det = detections[0]
            sx, sy = det["x"], det["y"]
            confidence = 0.95

            # Auto-rescue if survivor is at the drone's exact position
            if sx == dx and sy == dy:
                self._auto_rescue(did, sx, sy)

            return ScanResult(
                survivor_detected=True, confidence=confidence, x=sx, y=sy
            )

        return ScanResult(survivor_detected=False, confidence=0.0, x=dx, y=dy)

    async def return_to_base(self, drone_id: str) -> dict:
        did = self._to_int(drone_id)
        drone = self._world.get_drone(did)
        if drone is None:
            return {"success": False, "drone_id": drone_id}

        bx, by = self._world.base_pos
        self._world.move_drone_to(did, bx, by)
        drone.battery = 100.0
        from simulation.drone_agent import DroneState

        drone.state = DroneState.EXPLORE
        drone.known_survivors = []
        drone.known_edges = set()
        drone._goal = None

        return {
            "success": True,
            "drone_id": drone_id,
            "battery": 100,
            "state": "charging",
        }

    async def get_grid_map(self) -> GridMap:
        # Aggregate visited cells from all drones
        scanned: set[tuple[int, int]] = set()
        for agent in self._world.agents:  # pyright: ignore[reportAttributeAccessIssue]
            from simulation.drone_agent import DroneAgent

            if isinstance(agent, DroneAgent):
                scanned.update(agent.visited_cells)

        # Collect found survivors
        survivors: list[list[int]] = []
        for agent in self._world.agents:  # pyright: ignore[reportAttributeAccessIssue]
            from simulation.survivor import SurvivorAgent

            if isinstance(agent, SurvivorAgent) and agent.state.value != "unseen":
                sx, sy = agent._pos()
                survivors.append([sx, sy])

        return GridMap(
            scanned=[list(c) for c in sorted(scanned)],
            survivors=survivors,
        )

    async def broadcast_alert(self, x: int, y: int, message: str) -> dict:
        logger.info("ALERT at (%d, %d): %s", x, y, message)
        return {"success": True, "x": x, "y": y, "message": message}

    # ── helpers ──────────────────────────────────────────────────────

    def _auto_rescue(self, drone_id: int, sx: int, sy: int) -> None:
        """Mark a survivor as rescued if found at exact drone position."""
        from simulation.survivor import SurvivorAgent

        for agent in self._world.agents:  # pyright: ignore[reportAttributeAccessIssue]
            if isinstance(agent, SurvivorAgent):
                ax, ay = agent._pos()
                if ax == sx and ay == sy and agent.state.value == "found":
                    agent.mark_rescued(drone_id)
                    logger.info(
                        "Survivor #%d auto-rescued by drone %d at (%d,%d)",
                        agent.unique_id,
                        drone_id,
                        sx,
                        sy,
                    )
                    break
