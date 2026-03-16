"""
WebSocket event type definitions.

These TypedDicts define the JSON shape of every event the server pushes
to connected frontend clients.  The ``type`` discriminator field lets the
frontend dispatch on event kind without an explicit class hierarchy.
"""

from __future__ import annotations

from typing import Literal, TypedDict


class TickEvent(TypedDict):
    """Emitted every simulation tick — full world snapshot."""

    type: Literal["tick"]
    tick: int
    drones: list[dict]
    survivors: list[dict]
    obstacles: list[dict]
    coverage_pct: float
    base_pos: list[int]
    grid: dict
    mission_complete: bool


class MissionStatusEvent(TypedDict):
    """Emitted when mission lifecycle changes (started / stopped / error)."""

    type: Literal["mission_status"]
    status: str   # "started" | "stopped" | "error"
    message: str


class MissionCompleteEvent(TypedDict):
    """Emitted when all survivors are rescued."""

    type: Literal["mission_complete"]
    summary: dict


class ReasoningEvent(TypedDict):
    """Emitted when the LLM agent produces reasoning text."""

    type: Literal["reasoning"]
    step: int
    text: str


class ToolCallEvent(TypedDict):
    """Emitted after an MCP tool invocation completes."""

    type: Literal["tool_call"]
    tool_name: str
    params: dict
    result: dict


class SurvivorFoundEvent(TypedDict):
    """Emitted when a drone detects a survivor via thermal scan."""

    type: Literal["survivor_found"]
    x: int
    y: int
    confidence: float


class StepStartEvent(TypedDict):
    """Emitted at the beginning of each orchestrator reasoning step."""

    type: Literal["step_start"]
    step: int
    context: dict


class DroneStepLog(TypedDict):
    """Per-drone reasoning and state snapshot for a single tick."""

    drone_id: int
    state_before: str
    state_after: str
    pos_before: list[int]
    pos_after: list[int]
    battery_before: float
    battery_after: float
    visited_count: int
    known_survivors: list[int]
    known_edges_count: int
    target_survivor: int | None
    goal: list[int] | None
    reasoning: list[str]


class SimLogEvent(TypedDict):
    """Emitted every tick with per-drone reasoning chain of thought."""

    type: Literal["sim_log"]
    tick: int
    drone_logs: list[DroneStepLog]
