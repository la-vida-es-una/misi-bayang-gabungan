"""
Module-level application state singleton.

Holds the shared objects that route handlers and the WebSocket endpoint
need to access without threading through FastAPI's dependency injection:

- ``world``         — active SARWorld simulation (None until started)
- ``manager``       — WebSocket ConnectionManager (created once at import)
- ``mission_task``  — running asyncio.Task for the sim loop (None if idle)
- ``agent_logs``    — rolling buffer of agent/tool events for /mission/logs
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from api.websocket.manager import ConnectionManager

if TYPE_CHECKING:
    from simulation.world import SARWorld
    from agent.orchestrator import MissionOrchestrator


class AppState:
    def __init__(self) -> None:
        self.world: "SARWorld | None" = None
        self.manager: ConnectionManager = ConnectionManager()
        self.mission_task: asyncio.Task | None = None
        self.broadcaster_task: asyncio.Task | None = None
        self.agent_logs: list[dict] = []
        self.orchestrator: "MissionOrchestrator | None" = None


#: Global singleton — imported by route handlers and the WS endpoint.
app_state = AppState()
