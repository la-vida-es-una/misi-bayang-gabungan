from __future__ import annotations
import math
from typing import TYPE_CHECKING
from mesa import Agent

if TYPE_CHECKING:
    from .world import SARWorld


class ObstacleAgent(Agent):
    """
    Static blocking geometry in the disaster zone.

    Each obstacle occupies one or more grid cells. Drones cannot enter
    obstacle cells (enforced in DroneAgent movement logic).

    Obstacles also carry an *edge map* — a list of (cell_a, cell_b) pairs
    that represent the boundary between obstacle cells and free cells.
    Drones only discover the edges that fall within their vision radius,
    so large obstacles are revealed incrementally as the swarm explores.
    """

    def __init__(self, model: "SARWorld") -> None:
        super().__init__(model)
        # cells occupied by this obstacle — populated by SARWorld at init
        self.cells: list[tuple[int, int]] = []
        # boundary edges: list of ((x1,y1), (x2,y2)) free↔obstacle transitions
        self.edges: list[tuple[tuple[int, int], tuple[int, int]]] = []

    # ------------------------------------------------------------------
    # Mesa step — obstacles are passive
    # ------------------------------------------------------------------
    def step(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Edge discovery
    # ------------------------------------------------------------------
    def get_visible_edges(
        self,
        drone_x: int,
        drone_y: int,
        vision_radius: float,
    ) -> list[tuple[tuple[int, int], tuple[int, int]]]:
        """
        Return only the edges whose midpoint is within vision_radius of
        the given drone position. Drones call this each tick to build
        their incremental obstacle map.
        """
        visible = []
        for (ax, ay), (bx, by) in self.edges:
            mid_x = (ax + bx) / 2
            mid_y = (ay + by) / 2
            if math.hypot(mid_x - drone_x, mid_y - drone_y) <= vision_radius:
                visible.append(((ax, ay), (bx, by)))
        return visible

    def build_edges(self) -> None:
        """
        Compute boundary edges between this obstacle's cells and adjacent
        free cells. Called by SARWorld after all obstacle cells are assigned.
        """
        cell_set = set(self.cells)
        seen: set[tuple[tuple[int, int], tuple[int, int]]] = set()
        directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]

        for cx, cy in self.cells:
            for dx, dy in directions:
                nx, ny = cx + dx, cy + dy
                if (nx, ny) not in cell_set:
                    # (cx,cy) is obstacle, (nx,ny) is free — this is a boundary
                    edge = (min((cx, cy), (nx, ny)), max((cx, cy), (nx, ny)))
                    if edge not in seen:
                        seen.add(edge)
                        self.edges.append(((cx, cy), (nx, ny)))

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "id": self.unique_id,
            "cells": self.cells,
            "edges": [list(e) for e in self.edges],
        }
