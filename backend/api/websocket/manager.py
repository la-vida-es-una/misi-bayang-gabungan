"""
WebSocket connection manager.

Maintains the set of active WebSocket connections and provides a
broadcast method that fans out JSON events to every connected client.
Dead connections are silently pruned on the next broadcast attempt.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Fan-out WebSocket broadcaster.

    Usage::

        manager = ConnectionManager()

        # in the /ws endpoint:
        await manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await manager.disconnect(websocket)

        # from anywhere in the app:
        await manager.broadcast({"type": "tick", ...})
    """

    def __init__(self) -> None:
        self._active: set[WebSocket] = set()
        self._lock: asyncio.Lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self._active.add(websocket)
        logger.info("WS client connected — active: %d", len(self._active))

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket from the active set."""
        async with self._lock:
            self._active.discard(websocket)
        logger.info("WS client disconnected — active: %d", len(self._active))

    async def broadcast(self, event: dict) -> None:
        """Serialize *event* to JSON and send it to every active client.

        Connections that raise during send are collected and disconnected
        after the send loop to avoid modifying the set mid-iteration.
        """
        if not self._active:
            return

        payload = json.dumps(event, default=str)

        async with self._lock:
            targets = list(self._active)

        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)

        for ws in dead:
            await self.disconnect(ws)

    @property
    def client_count(self) -> int:
        """Number of currently connected clients."""
        return len(self._active)
