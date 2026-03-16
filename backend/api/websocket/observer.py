"""
WebSocket implementation of AgentObserverProtocol.

Bridges MissionOrchestrator events (reasoning, tool calls, survivor
detections, mission completion) to live WebSocket broadcasts so the
frontend dashboard receives AI agent updates in real time.

Inject an instance of this class into MissionOrchestrator::

    from api.websocket.observer import WebSocketObserver
    from api.state import app_state

    observer = WebSocketObserver(app_state.manager)
    orchestrator = MissionOrchestrator(mcp_client=client, observer=observer)
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from api.websocket.manager import ConnectionManager

logger = logging.getLogger(__name__)


class WebSocketObserver:
    """Satisfies AgentObserverProtocol and forwards every event to the WS manager."""

    def __init__(self, manager: "ConnectionManager") -> None:
        self._manager = manager

    # ── internal helper ──────────────────────────────────────────────

    def _fire(self, event: dict) -> None:
        """Schedule a broadcast on the running asyncio event loop (sync-safe)."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._manager.broadcast(event))
        except RuntimeError:
            logger.warning(
                "No running event loop — dropped WS event: %s", event.get("type")
            )

    # ── AgentObserverProtocol implementation ────────────────────────

    def on_step_start(self, step: int, context: dict) -> None:
        self._fire({"type": "step_start", "step": step, "context": context})

    def on_reasoning(self, step: int, text: str) -> None:
        self._fire({"type": "reasoning", "step": step, "text": text})

    def on_tool_call(self, tool_name: str, params: dict, result: dict) -> None:
        self._fire(
            {
                "type": "tool_call",
                "tool_name": tool_name,
                "params": params,
                "result": result,
            }
        )

    def on_survivor_found(self, x: int, y: int, confidence: float) -> None:
        self._fire(
            {"type": "survivor_found", "x": x, "y": y, "confidence": confidence}
        )

    def on_mission_complete(self, summary: dict) -> None:
        self._fire({"type": "mission_complete", "summary": summary})
