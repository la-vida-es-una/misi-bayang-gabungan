from enum import Enum
from mesa import Agent  # pyright: ignore[reportMissingTypeStubs]


class SurvivorState(str, Enum):
    UNSEEN = "unseen"
    FOUND = "found"
    RESCUED = "rescued"


class SurvivorAgent(Agent):  # pyright: ignore[reportMissingTypeArgument]
    """
    Stationary agent representing a disaster survivor.

    State machine:
        UNSEEN → FOUND (when any drone's vision radius overlaps this cell)
        FOUND  → RESCUED (when a DroneAgent reaches this cell)

    The survivor never moves. Its position is ground truth — unknown to
    drones until detection.
    """

    def __init__(self, model: "SARWorld") -> None:
        super().__init__(model)
        self.state: SurvivorState = SurvivorState.UNSEEN
        self.found_by: int | None = (
            None  # drone unique_id that first spotted this survivor
        )
        self.rescued_by: int | None = None  # drone unique_id that performed the rescue
        self.found_at_tick: int | None = None
        self.rescued_at_tick: int | None = None

    # ------------------------------------------------------------------
    # Mesa step — survivors are passive, state changes are driven by
    # DroneAgent logic, but we implement step() for Mesa's scheduler.
    # ------------------------------------------------------------------
    def step(self) -> None:
        pass

    # ------------------------------------------------------------------
    # State transitions (called by DroneAgent)
    # ------------------------------------------------------------------
    def mark_found(self, drone_id: int) -> None:
        if self.state == SurvivorState.UNSEEN:
            self.state = SurvivorState.FOUND
            self.found_by = drone_id
            self.found_at_tick = self.model.steps

    def mark_rescued(self, drone_id: int) -> None:
        if self.state == SurvivorState.FOUND:
            self.state = SurvivorState.RESCUED
            self.rescued_by = drone_id
            self.rescued_at_tick = self.model.steps

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
            "found_by": self.found_by,
            "rescued_by": self.rescued_by,
            "found_at_tick": self.found_at_tick,
            "rescued_at_tick": self.rescued_at_tick,
        }

    def _pos(self) -> tuple[int, int]:
        for agents, (x, y) in self.model.grid.coord_iter():
            for agent in agents:
                if agent is self:
                    return (x, y)
        return (-1, -1)
