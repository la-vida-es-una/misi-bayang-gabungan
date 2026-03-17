from __future__ import annotations

import math

import numpy as np
from mesa import Model
from mesa.space import MultiGrid

from .drone_agent import DroneAgent
from .obstacle import ObstacleAgent
from .survivor import SurvivorAgent


class _ScheduleCompat:
    def __init__(self, model: "SARWorld") -> None:
        self._model = model

    @property
    def agents(self) -> list:
        all_agents = list(self._model.agents)
        return sorted(
            all_agents,
            key=lambda agent: (
                0 if isinstance(agent, DroneAgent) else 1,
                getattr(agent, "unique_id", 0),
            ),
        )

    @property
    def time(self) -> int:
        return self._model.steps


class SARWorld(Model):
    """
    Mesa Model for the Stormwatch SAR simulation.

    Ground truth engine — the authoritative source of all agent positions,
    survivor states, and discovered geometry. The MCP server wraps this
    model's methods as tools exposed to the LLM agent.

    Parameters
    ----------
    n_drones : int
        Number of DroneAgents deployed at the base.
    n_survivors : int
        Survivors placed at random obstacle-free cells (positions unknown
        to drones until detected).
    width, height : int
        Grid dimensions in cells.
    n_obstacles : int
        Number of rectangular obstacle blocks to generate.
    vision_radius : float
        Drone detection radius in grid cells.
    comm_radius : float
        Drone-to-drone communication range in grid cells.
    battery_drain : float
        Battery lost per simulation tick.
    low_battery : float
        Battery level that triggers the Return state.
    speed : float
        Cells moved per tick (rounded to nearest int).
    seed : int | None
        Random seed for deterministic runs. Pass a fixed value for demos.
    """

    def __init__(
        self,
        n_drones: int = 5,
        n_survivors: int = 6,
        width: int = 100,
        height: int = 100,
        n_obstacles: int = 6,
        vision_radius: float = 8.0,
        comm_radius: float = 18.0,
        battery_drain: float = 0.9,
        low_battery: float = 20.0,
        speed: float = 1.0,
        seed: int | None = None,
    ) -> None:
        super().__init__(seed=seed)  # Mesa 2.x accepts seed directly

        self.rng = np.random.default_rng(seed)

        self.width = width
        self.height = height
        self.base_pos: tuple[int, int] = (2, height // 2)

        self.grid = MultiGrid(width, height, torus=False)
        # Mesa 2.x: no RandomActivation — self.agents (AgentSet) is built-in
        self.schedule = _ScheduleCompat(self)

        self._obstacle_cells: set[tuple[int, int]] = set()
        self._next_agent_id: int = 0

        self._place_obstacles(n_obstacles)
        self._place_survivors(n_survivors)
        self._place_drones(
            n_drones,
            vision_radius=vision_radius,
            comm_radius=comm_radius,
            battery_drain=battery_drain,
            low_battery=low_battery,
            speed=speed,
        )

        self.running = True

    def next_id(self) -> int:
        uid = self._next_agent_id
        self._next_agent_id += 1
        return uid

    # ------------------------------------------------------------------
    # Mesa tick
    # ------------------------------------------------------------------
    def step(self) -> None:
        # Mesa 2.x: shuffle_do replaces RandomActivation.step()
        self.agents.shuffle_do("step")

    # ------------------------------------------------------------------
    # World state snapshot (consumed by WebSocket broadcaster)
    # ------------------------------------------------------------------
    def get_state(self) -> dict:
        drones = []
        survivors = []
        obstacles = []

        for agent in self.agents:
            if isinstance(agent, DroneAgent):
                drones.append(agent.to_dict())
            elif isinstance(agent, SurvivorAgent):
                survivors.append(agent.to_dict())
            elif isinstance(agent, ObstacleAgent):
                obstacles.append(agent.to_dict())

        total_cells = self.width * self.height - len(self._obstacle_cells)
        visited: set[tuple[int, int]] = set()
        for agent in self.agents:
            if isinstance(agent, DroneAgent):
                visited.update(agent.visited_cells)
        coverage_pct = round(len(visited) / max(total_cells, 1) * 100, 1)

        return {
            "tick": self.steps,  # Mesa 2.x: .steps replaces .schedule.time
            "drones": drones,
            "survivors": survivors,
            "obstacles": obstacles,
            "coverage_pct": coverage_pct,
            "base_pos": list(self.base_pos),
            "grid": {"width": self.width, "height": self.height},
            "mission_complete": all(
                s.state.value == "rescued"
                for s in self.agents
                if isinstance(s, SurvivorAgent)
            ),
        }

    # ------------------------------------------------------------------
    # MCP tool helpers (called by mcp_server/tools/)
    # ------------------------------------------------------------------
    def get_drone(self, drone_id: int) -> DroneAgent | None:
        for agent in self.agents:
            if isinstance(agent, DroneAgent) and agent.unique_id == drone_id:
                return agent
        return None

    def list_active_drones(self) -> list[dict]:
        """Return serialised state of all drones with battery > 0."""
        return [
            agent.to_dict()
            for agent in self.agents
            if isinstance(agent, DroneAgent) and agent.battery > 0
        ]

    def move_drone_to(self, drone_id: int, x: int, y: int) -> dict:
        """
        Directly move a drone to (x, y) — internal method for initial placement.
        Returns updated drone state.
        """
        drone = self.get_drone(drone_id)
        if drone is None:
            return {"error": f"drone {drone_id} not found"}
        if self.is_blocked(x, y):
            return {"error": f"cell ({x},{y}) is blocked"}
        x = max(0, min(self.width - 1, x))
        y = max(0, min(self.height - 1, y))
        self.grid.move_agent(drone, (x, y))
        return drone.to_dict()

    def set_drone_waypoint(self, drone_id: int, x: int, y: int) -> dict:
        """Set a strategic waypoint for a drone. The drone's FSM will
        navigate there at its configured speed over subsequent ticks."""
        drone = self.get_drone(drone_id)
        if drone is None:
            return {"error": f"drone {drone_id} not found"}
        if self.is_blocked(x, y):
            return {"error": f"cell ({x},{y}) is blocked"}
        x = max(0, min(self.width - 1, x))
        y = max(0, min(self.height - 1, y))
        drone.set_llm_waypoint(x, y)
        result = drone.to_dict()
        result["waypoint_set"] = True
        result["target"] = [x, y]
        return result

    def command_drone_return(self, drone_id: int) -> dict:
        """Command a drone to return to base via its FSM (no teleport)."""
        drone = self.get_drone(drone_id)
        if drone is None:
            return {"error": f"drone {drone_id} not found"}
        drone.command_return_to_base()
        return drone.to_dict()

    def thermal_scan(self, drone_id: int) -> dict:
        """
        Return survivors visible within the drone's vision radius.
        Marks them as FOUND if previously UNSEEN.
        """
        drone = self.get_drone(drone_id)
        if drone is None:
            return {"error": f"drone {drone_id} not found"}
        dx, dy = drone._pos()
        results = []
        for agent in self.agents:
            if isinstance(agent, SurvivorAgent):
                sx, sy = agent._pos()
                if math.hypot(sx - dx, sy - dy) <= drone.vision_radius:
                    agent.mark_found(drone.unique_id)
                    results.append(agent.to_dict())
        return {"drone_id": drone_id, "detections": results}

    def is_blocked(self, x: int, y: int) -> bool:
        return (x, y) in self._obstacle_cells

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------
    def _free_cell(self) -> tuple[int, int]:
        """Return a random cell that is not an obstacle and not the base."""
        while True:
            # numpy rng uses integers(low, high) — high is exclusive
            x = int(self.rng.integers(0, self.width))
            y = int(self.rng.integers(0, self.height))
            if (x, y) not in self._obstacle_cells and (x, y) != self.base_pos:
                return (x, y)

    def _place_obstacles(self, n: int) -> None:
        for _ in range(n):
            # numpy rng: integers(low, high) — high is exclusive
            ox = int(self.rng.integers(10, self.width - 14))
            oy = int(self.rng.integers(5, self.height - 9))
            w = int(self.rng.integers(4, 15))  # 4..14 inclusive
            h = int(self.rng.integers(3, 11))  # 3..10 inclusive

            obstacle = ObstacleAgent(self)
            placed_anchor = False
            for cx in range(ox, min(ox + w, self.width)):
                for cy in range(oy, min(oy + h, self.height)):
                    if cx < 6:  # keep base corridor clear
                        continue
                    self._obstacle_cells.add((cx, cy))
                    obstacle.cells.append((cx, cy))
                    if not placed_anchor:
                        self.grid.place_agent(obstacle, (cx, cy))
                        placed_anchor = True

            obstacle.build_edges()
            # Mesa 2.x: no schedule.add() — agent registers itself via Agent.__init__

    def _place_survivors(self, n: int) -> None:
        for _ in range(n):
            pos = self._free_cell()
            survivor = SurvivorAgent(self)
            self.grid.place_agent(survivor, pos)

    def _place_drones(self, n: int, **kwargs) -> None:
        bx, by = self.base_pos
        for i in range(n):
            y_offset = i - n // 2
            pos = (bx, max(0, min(self.height - 1, by + y_offset)))
            drone = DroneAgent(self, **kwargs)
            self.grid.place_agent(drone, pos)
