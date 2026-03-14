"""
Mock MCP Client for independent agent development and testing.

Fully implements MCPClientProtocol with an internal simulated world:
- Configurable drones with battery drain
- Random survivor placement with thermal-scan detection
- Reproducible scenarios via seed parameter
"""

from __future__ import annotations

import random
from typing import Any

from colorama import Fore, Style

from .interfaces import DroneStatus, GridMap, MoveResult, ScanResult


class MockMCPClient:
    """
    Standalone mock that fully satisfies ``MCPClientProtocol``.

    Allows the agent team to develop and test with **zero** dependency on
    the real MCP server or simulation.

    Args:
        grid_size: Side length of the square grid (default 20).
        num_drones: Number of simulated drones (default 5).
        seed: Random seed for reproducible scenarios (``None`` = random).
    """

    def __init__(
        self,
        grid_size: int = 20,
        num_drones: int = 5,
        seed: int | None = None,
    ) -> None:
        self._grid_size = grid_size
        self._num_drones = num_drones
        self._seed = seed
        self._rng = random.Random(seed)

        # ── initialise world state ──────────────────────────────────
        self._drones: dict[str, dict[str, Any]] = {}
        self._survivors: set[tuple[int, int]] = set()
        self._scanned_coords: set[tuple[int, int]] = set()
        self._found_survivors: set[tuple[int, int]] = set()

        self._init_world()

    # ── world initialisation ────────────────────────────────────────

    def _init_world(self) -> None:
        """Populate drones and survivors from current RNG state."""
        self._drones.clear()
        self._survivors.clear()
        self._scanned_coords.clear()
        self._found_survivors.clear()

        for i in range(1, self._num_drones + 1):
            drone_id = f"drone_{i}"
            self._drones[drone_id] = {
                "drone_id": drone_id,
                "battery": self._rng.randint(50, 100),
                "x": self._rng.randint(0, self._grid_size - 1),
                "y": self._rng.randint(0, self._grid_size - 1),
                "state": "idle",
            }

        # Place 8 survivors at unique random positions
        while len(self._survivors) < 8:
            sx = self._rng.randint(0, self._grid_size - 1)
            sy = self._rng.randint(0, self._grid_size - 1)
            self._survivors.add((sx, sy))

        self._log(
            Fore.CYAN,
            "MOCK INIT",
            f"{self._num_drones} drones | 8 survivors | "
            f"grid {self._grid_size}x{self._grid_size} | seed={self._seed}",
        )

    # ── MCPClientProtocol implementation ────────────────────────────

    async def list_active_drones(self) -> dict[str, list[str]]:
        """Return all active (non-dead) drone IDs."""
        active = [
            did for did, d in self._drones.items() if d["state"] != "dead"
        ]
        self._log(Fore.BLUE, "list_active_drones", f"{len(active)} active")
        return {"drones": active}

    async def get_drone_status(self, drone_id: str) -> DroneStatus:
        """Return full status of a single drone."""
        drone = self._get_drone(drone_id)
        self._log(
            Fore.BLUE,
            "get_drone_status",
            f"{drone_id} → bat={drone['battery']}% pos=({drone['x']},{drone['y']}) "
            f"state={drone['state']}",
        )
        return DroneStatus(
            drone_id=drone["drone_id"],
            battery=drone["battery"],
            x=drone["x"],
            y=drone["y"],
            state=drone["state"],
        )

    async def move_to(self, drone_id: str, x: int, y: int) -> MoveResult:
        """Move drone to coordinates. Drains 3% battery per move."""
        drone = self._get_drone(drone_id)

        if drone["state"] == "dead":
            self._log(Fore.RED, "move_to", f"{drone_id} is DEAD — cannot move")
            return MoveResult(success=False, drone_id=drone_id, x=drone["x"], y=drone["y"])

        drone["battery"] = max(0, drone["battery"] - 3)
        if drone["battery"] <= 0:
            drone["state"] = "dead"
            self._log(Fore.RED, "move_to", f"{drone_id} battery DEPLETED → dead")
            return MoveResult(success=False, drone_id=drone_id, x=drone["x"], y=drone["y"])

        x = max(0, min(x, self._grid_size - 1))
        y = max(0, min(y, self._grid_size - 1))
        drone["x"] = x
        drone["y"] = y
        drone["state"] = "moving"
        self._scanned_coords.add((x, y))

        self._log(
            Fore.YELLOW,
            "move_to",
            f"{drone_id} → ({x},{y}) | bat={drone['battery']}%",
        )
        return MoveResult(success=True, drone_id=drone_id, x=x, y=y)

    async def thermal_scan(self, drone_id: str) -> ScanResult:
        """
        Thermal scan at drone's current position.

        Returns ``survivor_detected=True`` (confidence 0.85–0.99)
        if a survivor exists within 1 cell of the drone.  Battery drains 1%.
        """
        drone = self._get_drone(drone_id)

        if drone["state"] == "dead":
            self._log(Fore.RED, "thermal_scan", f"{drone_id} is DEAD — cannot scan")
            return ScanResult(survivor_detected=False, confidence=0.0, x=drone["x"], y=drone["y"])

        drone["battery"] = max(0, drone["battery"] - 1)
        if drone["battery"] <= 0:
            drone["state"] = "dead"
            self._log(Fore.RED, "thermal_scan", f"{drone_id} battery DEPLETED → dead")
            return ScanResult(survivor_detected=False, confidence=0.0, x=drone["x"], y=drone["y"])

        drone["state"] = "scanning"
        dx, dy = drone["x"], drone["y"]

        # Check adjacency (within 1 cell in each direction)
        for sx, sy in self._survivors:
            if abs(sx - dx) <= 1 and abs(sy - dy) <= 1:
                confidence = round(self._rng.uniform(0.85, 0.99), 2)
                self._found_survivors.add((sx, sy))
                self._log(
                    Fore.GREEN,
                    "thermal_scan",
                    f"🔥 SURVIVOR DETECTED at ({sx},{sy}) conf={confidence} "
                    f"by {drone_id}",
                )
                return ScanResult(
                    survivor_detected=True, confidence=confidence, x=sx, y=sy
                )

        self._log(
            Fore.WHITE,
            "thermal_scan",
            f"{drone_id} at ({dx},{dy}) — no survivor nearby",
        )
        return ScanResult(survivor_detected=False, confidence=0.0, x=dx, y=dy)

    async def return_to_base(self, drone_id: str) -> dict:
        """Recall drone to base. Simulates recharge to 100%."""
        drone = self._get_drone(drone_id)
        old_battery = drone["battery"]
        drone["state"] = "returning"
        drone["x"] = 0
        drone["y"] = 0
        drone["battery"] = 100
        drone["state"] = "charging"

        self._log(
            Fore.MAGENTA,
            "return_to_base",
            f"{drone_id} recalled (was {old_battery}%) → recharged 100%",
        )
        return {
            "success": True,
            "drone_id": drone_id,
            "battery": 100,
            "state": "charging",
        }

    async def get_grid_map(self) -> GridMap:
        """Return current known state of the full grid."""
        scanned = [list(c) for c in sorted(self._scanned_coords)]
        survivors = [list(c) for c in sorted(self._found_survivors)]
        self._log(
            Fore.CYAN,
            "get_grid_map",
            f"scanned={len(scanned)} cells | survivors_found={len(survivors)}",
        )
        return GridMap(scanned=scanned, survivors=survivors)

    async def broadcast_alert(self, x: int, y: int, message: str) -> dict:
        """Broadcast survivor alert to all units."""
        self._log(
            Fore.GREEN,
            "broadcast_alert",
            f"📡 ALERT at ({x},{y}): {message}",
        )
        return {"success": True, "x": x, "y": y, "message": message}

    # ── helper / debug methods ──────────────────────────────────────

    def reset(self, seed: int | None = None) -> None:
        """Reset world state. Useful for running multiple test scenarios."""
        if seed is not None:
            self._seed = seed
        self._rng = random.Random(self._seed)
        self._init_world()
        self._log(Fore.CYAN, "RESET", f"World reset with seed={self._seed}")

    def get_world_state(self) -> dict:
        """Return full internal state for debugging / test assertions."""
        return {
            "grid_size": self._grid_size,
            "drones": {did: dict(d) for did, d in self._drones.items()},
            "survivors": [list(s) for s in sorted(self._survivors)],
            "found_survivors": [list(s) for s in sorted(self._found_survivors)],
            "scanned_coords": [list(c) for c in sorted(self._scanned_coords)],
        }

    def inject_low_battery(self, drone_id: str) -> None:
        """Set a specific drone to 15% battery — for triggering battery guardian tests."""
        drone = self._get_drone(drone_id)
        drone["battery"] = 15
        self._log(
            Fore.RED,
            "inject_low_battery",
            f"{drone_id} → 15% battery (test injection)",
        )

    # ── internal helpers ────────────────────────────────────────────

    def _get_drone(self, drone_id: str) -> dict[str, Any]:
        """Look up a drone by ID, raise ValueError if not found."""
        if drone_id not in self._drones:
            raise ValueError(
                f"Unknown drone '{drone_id}'. "
                f"Available: {list(self._drones.keys())}"
            )
        return self._drones[drone_id]

    @staticmethod
    def _log(color: str, tag: str, message: str) -> None:
        """Print coloured status line to terminal."""
        print(f"{color}[MOCK {tag}]{Style.RESET_ALL} {message}")
