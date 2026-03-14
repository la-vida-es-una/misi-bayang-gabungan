"""
Sector-based mission planner with lawnmower / snake waypoint generation.

Divides the grid into four quadrants (A–D) and manages drone-to-sector
assignments, waypoint sequences, and coverage tracking.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Sector:
    """A rectangular region of the grid."""

    name: str
    x_min: int
    x_max: int
    y_min: int
    y_max: int
    assigned_drone: str | None = None
    scanned_coords: set[tuple[int, int]] = field(default_factory=set)

    @property
    def total_cells(self) -> int:
        """Total number of cells in this sector."""
        return (self.x_max - self.x_min + 1) * (self.y_max - self.y_min + 1)

    @property
    def coverage(self) -> float:
        """Fraction of cells scanned (0.0 – 1.0)."""
        total = self.total_cells
        if total == 0:
            return 1.0
        return len(self.scanned_coords) / total


@dataclass
class WaypointPlan:
    """Ordered list of waypoints a drone should visit in its assigned sector."""

    drone_id: str
    sector: str
    waypoints: list[tuple[int, int]]
    current_index: int = 0


class SectorPlanner:
    """
    Manages sector assignment, waypoint generation, and coverage tracking
    for a grid divided into four quadrants.

    Sector layout (default 20×20):
        A : x=[0..9],  y=[0..9]   (bottom-left)
        B : x=[10..19], y=[0..9]   (bottom-right)
        C : x=[0..9],  y=[10..19]  (top-left)
        D : x=[10..19], y=[10..19] (top-right)
    """

    def __init__(self, grid_size: int = 20) -> None:
        self._grid_size = grid_size
        half = grid_size // 2

        self._sectors: dict[str, Sector] = {
            "A": Sector("A", 0, half - 1, 0, half - 1),
            "B": Sector("B", half, grid_size - 1, 0, half - 1),
            "C": Sector("C", 0, half - 1, half, grid_size - 1),
            "D": Sector("D", half, grid_size - 1, half, grid_size - 1),
        }

        # Drone → sector name mapping
        self._drone_sectors: dict[str, str] = {}
        # Drone → WaypointPlan
        self._waypoint_plans: dict[str, WaypointPlan] = {}

    # ── assignment ──────────────────────────────────────────────────

    def assign_sector(self, drone_id: str) -> str | None:
        """
        Assign the next unassigned sector to a drone.

        Returns the sector name, or ``None`` if all sectors are taken.
        """
        for name, sector in self._sectors.items():
            if sector.assigned_drone is None:
                sector.assigned_drone = drone_id
                self._drone_sectors[drone_id] = name

                # Pre-generate waypoints
                waypoints = self.get_next_waypoints(name)
                self._waypoint_plans[drone_id] = WaypointPlan(
                    drone_id=drone_id, sector=name, waypoints=waypoints
                )
                return name
        return None

    def release_sector(self, drone_id: str) -> None:
        """Release a drone's sector assignment so another drone can take it."""
        sector_name = self._drone_sectors.pop(drone_id, None)
        if sector_name and sector_name in self._sectors:
            self._sectors[sector_name].assigned_drone = None
        self._waypoint_plans.pop(drone_id, None)

    def get_drone_assignment(self, drone_id: str) -> str | None:
        """Return the sector name assigned to a drone, or ``None``."""
        return self._drone_sectors.get(drone_id)

    # ── waypoints ───────────────────────────────────────────────────

    def get_next_waypoints(self, sector_name: str) -> list[tuple[int, int]]:
        """
        Generate a snake / lawnmower pattern covering every cell in the sector.

        Even rows go left→right, odd rows go right→left.
        """
        sector = self._sectors[sector_name]
        waypoints: list[tuple[int, int]] = []

        row_index = 0
        for y in range(sector.y_min, sector.y_max + 1):
            if row_index % 2 == 0:
                xs = range(sector.x_min, sector.x_max + 1)
            else:
                xs = range(sector.x_max, sector.x_min - 1, -1)
            for x in xs:
                waypoints.append((x, y))
            row_index += 1

        return waypoints

    def get_next_waypoint(self, drone_id: str) -> tuple[int, int] | None:
        """
        Return the next waypoint for a drone and advance its index.

        Returns ``None`` when all waypoints have been visited.
        """
        plan = self._waypoint_plans.get(drone_id)
        if plan is None:
            return None
        if plan.current_index >= len(plan.waypoints):
            return None

        wp = plan.waypoints[plan.current_index]
        plan.current_index += 1
        return wp

    # ── scanning / coverage ─────────────────────────────────────────

    def mark_scanned(self, x: int, y: int) -> None:
        """Record a coordinate as scanned in the appropriate sector."""
        for sector in self._sectors.values():
            if (
                sector.x_min <= x <= sector.x_max
                and sector.y_min <= y <= sector.y_max
            ):
                sector.scanned_coords.add((x, y))
                return

    def coverage_percent(self) -> float:
        """Overall grid coverage as a fraction (0.0 – 1.0)."""
        total_cells = self._grid_size * self._grid_size
        scanned = sum(len(s.scanned_coords) for s in self._sectors.values())
        return scanned / total_cells if total_cells > 0 else 1.0

    def get_unscanned_sectors(self) -> list[str]:
        """Return names of sectors with coverage below 95%."""
        return [
            name
            for name, sector in self._sectors.items()
            if sector.coverage < 0.95
        ]

    def all_sectors_scanned(self) -> bool:
        """True if every sector has ≥ 95% coverage."""
        return all(s.coverage >= 0.95 for s in self._sectors.values())

    # ── reporting ───────────────────────────────────────────────────

    def get_status_report(self) -> dict:
        """Return full planner state as a dict for context injection."""
        return {
            "grid_size": self._grid_size,
            "overall_coverage": round(self.coverage_percent() * 100, 1),
            "all_scanned": self.all_sectors_scanned(),
            "sectors": {
                name: {
                    "coverage": round(sector.coverage * 100, 1),
                    "assigned_drone": sector.assigned_drone,
                    "scanned_count": len(sector.scanned_coords),
                    "total_cells": sector.total_cells,
                    "bounds": {
                        "x_min": sector.x_min,
                        "x_max": sector.x_max,
                        "y_min": sector.y_min,
                        "y_max": sector.y_max,
                    },
                }
                for name, sector in self._sectors.items()
            },
            "drone_assignments": dict(self._drone_sectors),
        }
