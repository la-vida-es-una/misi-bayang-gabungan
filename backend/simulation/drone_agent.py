from __future__ import annotations
import math
from enum import Enum
from typing import TYPE_CHECKING
from mesa import Agent

if TYPE_CHECKING:
    from .world import SARWorld

from simulation.survivor import SurvivorAgent, SurvivorState


class DroneState(str, Enum):
    EXPLORE = "explore"
    CONVERGE = "converge"
    RETURN = "return"


class DroneAgent(Agent):
    """
    Autonomous rescue drone with a three-state FSM.

    States
    ------
    EXPLORE
        Steers toward unvisited grid cells. Detects survivors and obstacle
        edges within vision_radius. Shares discoveries with nearby drones
        over the comm mesh. Switches to CONVERGE when a survivor is known.

    CONVERGE
        Pursues a known survivor's cell. On arrival, marks the survivor
        as RESCUED and transitions to RETURN. Also transitions to RETURN
        if battery falls below low_battery threshold.

    RETURN
        Flies back to the base cell. On arrival, recharges battery to 100,
        clears personal knowledge, and re-enters EXPLORE.

    Attributes
    ----------
    battery : float
        Percentage (0–100). Decreases by battery_drain each tick.
    visited_cells : set[tuple[int,int]]
        Cells this drone has personally scanned.
    known_survivors : list[SurvivorAgent]
        Survivors this drone knows about (own detection + comm mesh).
    known_edges : set[tuple]
        Obstacle edges this drone has sampled.
    target_survivor : SurvivorAgent | None
        The survivor currently being pursued in CONVERGE state.
    """

    def __init__(
        self,
        model: "SARWorld",
        vision_radius: float = 8.0,
        comm_radius: float = 18.0,
        battery_drain: float = 0.9,
        low_battery: float = 20.0,
        speed: float = 1.0,
    ) -> None:
        super().__init__(model)
        self.vision_radius = vision_radius
        self.comm_radius = comm_radius
        self.battery_drain = battery_drain
        self.low_battery = low_battery
        self.speed = speed

        self.state: DroneState = DroneState.EXPLORE
        self.battery: float = 100.0

        self.visited_cells: set[tuple[int, int]] = set()
        self.known_survivors: list[SurvivorAgent] = []  # SurvivorAgent refs
        self.known_edges: set[tuple] = set()  # frozenset edge keys

        self.target_survivor = None
        self._goal: tuple[int, int] | None = None
        self._llm_waypoint: tuple[int, int] | None = None
        self._last_step_log: dict = {}

    # ------------------------------------------------------------------
    # LLM command interface
    # ------------------------------------------------------------------
    def set_llm_waypoint(self, x: int, y: int) -> None:
        """Accept a strategic waypoint from the LLM orchestrator.
        The drone FSM will navigate there at its configured speed."""
        self._llm_waypoint = (x, y)
        self._goal = (x, y)

    def command_return_to_base(self) -> None:
        """LLM commands this drone to return to base.
        Sets state to RETURN so the FSM flies it back at normal speed."""
        self.state = DroneState.RETURN
        self._llm_waypoint = None

    # ------------------------------------------------------------------
    # Mesa step
    # ------------------------------------------------------------------
    def step(self) -> None:
        prev_state = self.state
        prev_battery = self.battery
        pos = self._pos()

        self._drain_battery()
        self.visited_cells.add(pos)

        # Sensing phase — track new detections
        prev_known = len(self.known_survivors)
        prev_edges = len(self.known_edges)
        self._sense(pos)
        new_detections = len(self.known_survivors) - prev_known
        new_edges = len(self.known_edges) - prev_edges

        # Communication phase — track shared intel
        pre_comm_survivors = len(self.known_survivors)
        pre_comm_edges = len(self.known_edges)
        self._communicate(pos)
        shared_survivors = len(self.known_survivors) - pre_comm_survivors
        shared_edges = len(self.known_edges) - pre_comm_edges

        # FSM transition
        if self.state == DroneState.EXPLORE:
            self._step_explore(pos)
        elif self.state == DroneState.CONVERGE:
            self._step_converge(pos)
        elif self.state == DroneState.RETURN:
            self._step_return(pos)

        new_pos = self._pos()

        # Build step log entry
        self._last_step_log = self._build_step_log(
            prev_state=prev_state,
            prev_battery=prev_battery,
            pos_before=pos,
            pos_after=new_pos,
            new_detections=new_detections,
            new_edges=new_edges,
            shared_survivors=shared_survivors,
            shared_edges=shared_edges,
        )

    def _build_step_log(
        self,
        *,
        prev_state: DroneState,
        prev_battery: float,
        pos_before: tuple[int, int],
        pos_after: tuple[int, int],
        new_detections: int,
        new_edges: int,
        shared_survivors: int,
        shared_edges: int,
    ) -> dict:
        """Build a reasoning/chain-of-thought log entry for this step."""
        log: dict = {
            "drone_id": self.unique_id,
            "state_before": prev_state.value,
            "state_after": self.state.value,
            "pos_before": list(pos_before),
            "pos_after": list(pos_after),
            "battery_before": round(prev_battery, 1),
            "battery_after": round(self.battery, 1),
            "visited_count": len(self.visited_cells),
            "known_survivors": [s.unique_id for s in self.known_survivors],
            "known_edges_count": len(self.known_edges),
            "target_survivor": (
                self.target_survivor.unique_id if self.target_survivor else None
            ),
            "goal": list(self._goal) if self._goal else None,
            "reasoning": [],
        }

        reasoning: list[str] = log["reasoning"]

        # Battery
        drain = round(prev_battery - self.battery, 2)
        reasoning.append(f"Battery drained {drain}% -> {round(self.battery, 1)}%")

        # Sensing
        if new_detections > 0:
            reasoning.append(f"Thermal scan detected {new_detections} new survivor(s)")
        if new_edges > 0:
            reasoning.append(f"Sampled {new_edges} new obstacle edge(s)")

        # Communication
        if shared_survivors > 0 or shared_edges > 0:
            parts = []
            if shared_survivors > 0:
                parts.append(f"{shared_survivors} survivor(s)")
            if shared_edges > 0:
                parts.append(f"{shared_edges} edge(s)")
            reasoning.append(f"Comm mesh received: {', '.join(parts)}")

        # FSM transition reasoning
        transitioned = prev_state != self.state
        if transitioned:
            reasoning.append(
                f"FSM transition: {prev_state.value} -> {self.state.value}"
            )
            if prev_state == DroneState.EXPLORE and self.state == DroneState.CONVERGE:
                reasoning.append(
                    f"Unrescued survivor detected — converging on survivor #{self.target_survivor.unique_id if self.target_survivor else '?'}"
                )
            elif prev_state == DroneState.EXPLORE and self.state == DroneState.RETURN:
                reasoning.append(
                    f"Low battery ({round(self.battery, 1)}% <= {self.low_battery}%) — returning to base"
                )
            elif prev_state == DroneState.CONVERGE and self.state == DroneState.RETURN:
                if self.battery <= self.low_battery:
                    reasoning.append(
                        "Low battery during convergence — returning to base"
                    )
                else:
                    reasoning.append(
                        "Survivor rescued — returning to base for recharge"
                    )
            elif prev_state == DroneState.CONVERGE and self.state == DroneState.EXPLORE:
                reasoning.append("Target already rescued — resuming exploration")
            elif prev_state == DroneState.RETURN and self.state == DroneState.EXPLORE:
                reasoning.append(
                    "Arrived at base — recharged to 100% — resuming exploration"
                )
        else:
            # Same state reasoning
            if self.state == DroneState.EXPLORE:
                if self._goal:
                    reasoning.append(
                        f"Exploring toward goal ({self._goal[0]}, {self._goal[1]})"
                    )
                else:
                    reasoning.append("Exploring — selecting new goal")
            elif self.state == DroneState.CONVERGE:
                if self.target_survivor:
                    tp = self.target_survivor._pos()
                    reasoning.append(
                        f"Converging on survivor #{self.target_survivor.unique_id} at ({tp[0]}, {tp[1]})"
                    )
            elif self.state == DroneState.RETURN:
                reasoning.append(
                    f"Returning to base at ({self.model.base_pos[0]}, {self.model.base_pos[1]})"
                )

        # Movement
        if pos_before != pos_after:
            reasoning.append(
                f"Moved ({pos_before[0]},{pos_before[1]}) -> ({pos_after[0]},{pos_after[1]})"
            )
        else:
            reasoning.append("No movement this tick (blocked or at destination)")

        # LLM waypoint
        if self._llm_waypoint:
            reasoning.append(
                f"LLM waypoint active: ({self._llm_waypoint[0]}, {self._llm_waypoint[1]})"
            )

        return log

    # ------------------------------------------------------------------
    # FSM steps
    # ------------------------------------------------------------------
    def _step_explore(self, pos: tuple[int, int]) -> None:
        if self.battery <= self.low_battery:
            self.state = DroneState.RETURN
            self._llm_waypoint = None
            return

        unrescued = [s for s in self.known_survivors if s.state.value == "found"]
        if unrescued:
            self.target_survivor = min(
                unrescued,
                key=lambda s: math.hypot(*self._vec_to(s._pos(), pos)),
            )
            self.state = DroneState.CONVERGE
            self._llm_waypoint = None
            return

        # LLM waypoint takes priority over self-selected exploration goal
        if self._llm_waypoint:
            if pos == self._llm_waypoint:
                self._llm_waypoint = None
                self._goal = self._pick_explore_goal(pos)
            else:
                self._goal = self._llm_waypoint
        elif not self._goal or pos == self._goal:
            self._goal = self._pick_explore_goal(pos)

        self._move_toward(self._goal)

    def _step_converge(self, pos: tuple[int, int]) -> None:
        if self.battery <= self.low_battery:
            self.target_survivor = None
            self.state = DroneState.RETURN
            return

        if not self.target_survivor or self.target_survivor.state.value == "rescued":
            self.target_survivor = None
            self.state = DroneState.EXPLORE
            return

        target_pos = self.target_survivor._pos()
        if pos == target_pos:
            self.target_survivor.mark_rescued(self.unique_id)
            self.known_survivors = [
                s for s in self.known_survivors if s is not self.target_survivor
            ]
            self.target_survivor = None
            self.state = DroneState.RETURN
            return

        self._move_toward(target_pos)

    def _step_return(self, pos: tuple[int, int]) -> None:
        base = self.model.base_pos
        if pos == base:
            self.battery = 100.0
            self.known_survivors = []
            self.known_edges = set()
            self._goal = None
            self.state = DroneState.EXPLORE
            return
        self._move_toward(base)

    # ------------------------------------------------------------------
    # Sensing
    # ------------------------------------------------------------------
    def _sense(self, pos: tuple[int, int]) -> None:
        x, y = pos
        # detect survivors
        for agent in self.model.agents:
            from .survivor import SurvivorAgent

            if (
                isinstance(agent, SurvivorAgent)
                and agent.state != SurvivorState.RESCUED
            ):
                ax, ay = agent._pos()
                if math.hypot(ax - x, ay - y) <= self.vision_radius:
                    if agent.state == SurvivorState.UNSEEN:
                        agent.mark_found(self.unique_id)
                    if agent not in self.known_survivors:
                        self.known_survivors.append(agent)

        # sample obstacle edges
        for agent in self.model.agents:
            from .obstacle import ObstacleAgent

            if isinstance(agent, ObstacleAgent):
                for edge in agent.get_visible_edges(x, y, self.vision_radius):
                    key = (min(edge[0], edge[1]), max(edge[0], edge[1]))
                    self.known_edges.add(key)

    # ------------------------------------------------------------------
    # Communication mesh
    # ------------------------------------------------------------------
    def _communicate(self, pos: tuple[int, int]) -> None:
        x, y = pos
        from .survivor import SurvivorAgent

        for agent in self.model.agents:
            if not isinstance(agent, DroneAgent) or agent is self:
                continue
            ox, oy = agent._pos()
            if math.hypot(ox - x, oy - y) <= self.comm_radius:
                # share survivors
                for s in agent.known_survivors:
                    if s not in self.known_survivors:
                        self.known_survivors.append(s)
                # share edges
                self.known_edges.update(agent.known_edges)

    # ------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------
    def _move_toward(self, goal: tuple[int, int]) -> None:
        pos = self._pos()
        if pos == goal:
            return
        dx, dy = self._vec_to(goal, pos)
        steps = max(1, round(self.speed))
        cx, cy = pos
        for _ in range(steps):
            nx = cx + (1 if dx > 0 else -1 if dx < 0 else 0)
            ny = cy + (1 if dy > 0 else -1 if dy < 0 else 0)
            nx = max(0, min(self.model.grid.width - 1, nx))
            ny = max(0, min(self.model.grid.height - 1, ny))
            if not self.model.is_blocked(nx, ny):
                self.model.grid.move_agent(self, (nx, ny))
                cx, cy = nx, ny
                dx, dy = self._vec_to(goal, (cx, cy))
            else:
                # try axis-aligned detour
                if not self.model.is_blocked(nx, cy):
                    self.model.grid.move_agent(self, (nx, cy))
                    cx, cy = nx, cy
                elif not self.model.is_blocked(cx, ny):
                    self.model.grid.move_agent(self, (cx, ny))
                    cx, cy = cx, ny
                else:
                    break

    def _pick_explore_goal(self, pos: tuple[int, int]) -> tuple[int, int]:
        """Score candidate cells: prefer unvisited, prefer spread from other drones."""
        best, best_score = pos, -1.0
        w, h = self.model.grid.width, self.model.grid.height
        for _ in range(30):
            gx = self.random.randint(0, w - 1)
            gy = self.random.randint(0, h - 1)
            if self.model.is_blocked(gx, gy):
                continue
            unvisited_bonus = 0 if (gx, gy) in self.visited_cells else 150
            spread = sum(
                math.hypot(gx - a._pos()[0], gy - a._pos()[1])
                for a in self.model.agents
                if isinstance(a, DroneAgent) and a is not self
            )
            score = unvisited_bonus + spread * 0.3 + self.random.uniform(0, 25)
            if score > best_score:
                best_score = score
                best = (gx, gy)
        return best

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _drain_battery(self) -> None:
        self.battery = max(0.0, self.battery - self.battery_drain)

    def _pos(self) -> tuple[int, int]:
        return self.model.grid.find_empty()  # overridden below

    def _vec_to(
        self, goal: tuple[int, int], origin: tuple[int, int]
    ) -> tuple[int, int]:
        return goal[0] - origin[0], goal[1] - origin[1]

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        x, y = self._pos()
        return {
            "id": self.unique_id,
            "x": x,
            "y": y,
            "state": self.state.value,
            "battery": round(self.battery, 1),
            "visited_cells": len(self.visited_cells),
            "known_survivors": [s.unique_id for s in self.known_survivors],
            "known_edges": len(self.known_edges),
            "target_survivor": (
                self.target_survivor.unique_id if self.target_survivor else None
            ),
            "llm_waypoint": list(self._llm_waypoint) if self._llm_waypoint else None,
        }


# ------------------------------------------------------------------
# Monkey-patch _pos to use Mesa grid properly
# ------------------------------------------------------------------
def _real_pos(self) -> tuple[int, int]:
    for content, (x, y) in self.model.grid.coord_iter():
        for agent in content:
            if agent is self:
                return (x, y)
    return (-1, -1)


DroneAgent._pos = _real_pos  # type: ignore[method-assign]
