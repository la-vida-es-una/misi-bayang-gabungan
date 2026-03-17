"""
RealMCPClient — implements MCPClientProtocol via genuine MCP protocol.

Uses fastmcp.Client to dispatch all drone commands through the FastMCP
server's tool registry and MCP message serialization stack. This satisfies
the mandatory constraint that all LLM↔Drone communication must go via MCP.

Unlike LiveMCPClient (which calls SARWorld Python methods directly),
RealMCPClient's calls go through the full MCP tool dispatch path:

    LangChain tool → RealMCPClient method
        → fastmcp.Client.call_tool()
            → FastMCP tool registry (mcp_server/tools/)
                → SARWorld method
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from fastmcp import Client

from .interfaces import DroneStatus, GridMap, MoveResult, ScanResult

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = logging.getLogger(__name__)


class RealMCPClient:
    """
    Implements MCPClientProtocol by routing all calls through FastMCP in-process.

    All seven protocol methods call the corresponding MCP tool by name via
    ``fastmcp.Client``. The call goes through FastMCP's tool registry and MCP
    message serialization — genuine MCP protocol communication.

    Args:
        mcp: The ``FastMCP`` server instance from ``mcp_server.context``.
    """

    def __init__(self, mcp: "FastMCP") -> None:
        self._mcp = mcp

    # ── ID translation ───────────────────────────────────────────────

    @staticmethod
    def _to_int(drone_id: str) -> int:
        """'drone_6' -> 6.  Also accepts bare integers ('6')."""
        if "_" in drone_id:
            parts = drone_id.split("_")
            if len(parts) >= 2 and parts[1]:
                return int(parts[1])
        return int(drone_id)

    @staticmethod
    def _to_str(drone_id: int) -> str:
        """6 -> 'drone_6'"""
        return f"drone_{drone_id}"

    # ── MCP dispatch helper ──────────────────────────────────────────

    async def _call(self, tool: str, args: dict) -> dict:
        """
        Call an MCP tool by name and return the parsed response dict.

        Opens a short-lived in-process FastMCP client session, dispatches
        the tool call through the MCP protocol stack, and returns the result.

        FastMCP 3.x returns a CallToolResult object (not a list) with:
          .data            — already-parsed Python dict (used directly)
          .is_error        — True when the tool raised an exception
          .content         — list of TextContent items (fallback)
        """
        async with Client(self._mcp) as client:
            result = await client.call_tool(tool, args)

        if result.is_error:
            logger.warning("MCP tool %r returned error: %r", tool, result)
            return {}

        # Prefer .data — FastMCP 3.x populates this with the parsed return value
        if result.data is not None:
            return result.data if isinstance(result.data, dict) else {}

        # Fallback to text content if .data is absent
        if result.content:
            text = getattr(result.content[0], "text", None)
            if text:
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    logger.warning("MCP tool %r non-JSON text: %r", tool, text)

        logger.warning("MCP tool %r returned empty result", tool)
        return {}

    # ── MCPClientProtocol implementation ─────────────────────────────

    async def list_active_drones(self) -> dict[str, list[str]]:
        data = await self._call("list_active_drones", {})
        # MCP server returns integer IDs → convert to "drone_N" strings
        return {"drones": [self._to_str(d) for d in data.get("drones", [])]}

    async def get_drone_status(self, drone_id: str) -> DroneStatus:
        data = await self._call("get_drone_status", {"drone_id": self._to_int(drone_id)})
        return DroneStatus(
            drone_id=drone_id,
            battery=int(data.get("battery", 0)),
            x=data.get("x", 0),
            y=data.get("y", 0),
            state=data.get("state", "unknown"),
        )

    async def move_to(self, drone_id: str, x: int, y: int) -> MoveResult:
        data = await self._call(
            "move_to", {"drone_id": self._to_int(drone_id), "x": x, "y": y}
        )
        success = "error" not in data
        return MoveResult(success=success, drone_id=drone_id, x=x, y=y)

    async def thermal_scan(self, drone_id: str) -> ScanResult:
        data = await self._call("thermal_scan", {"drone_id": self._to_int(drone_id)})
        detected = data.get("survivor_detected", False)
        detections = data.get("detections", [])
        if detected and detections:
            det = detections[0]
            return ScanResult(
                survivor_detected=True,
                confidence=data.get("confidence", 0.95),
                x=det.get("x", 0),
                y=det.get("y", 0),
            )
        return ScanResult(
            survivor_detected=False,
            confidence=0.0,
            x=data.get("x", 0),
            y=data.get("y", 0),
        )

    async def return_to_base(self, drone_id: str) -> dict:
        data = await self._call("return_to_base", {"drone_id": self._to_int(drone_id)})
        return {
            "success": "error" not in data,
            "drone_id": drone_id,
            "battery": data.get("battery", 0),
            "state": data.get("state", "returning"),
        }

    async def get_grid_map(self) -> GridMap:
        data = await self._call("get_grid_map", {})
        return GridMap(
            scanned=data.get("scanned", []),
            survivors=data.get("survivors", []),
        )

    async def broadcast_alert(self, x: int, y: int, message: str) -> dict:
        return await self._call("broadcast_alert", {"x": x, "y": y, "message": message})
