"""
Mission Orchestrator — primary entry point for all teams.

Wires together:
- LangGraph ReAct agent with tool-wrapped MCP protocol methods
- Battery guardian (autonomous recall without LLM)
- Sector planner (waypoint-based coverage)
- Mission logger + observer bridge
- Context builder + history compression

Uses ``langgraph.prebuilt.create_react_agent`` (LangChain v1+ API).
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool as langchain_tool
from langgraph.prebuilt import create_react_agent

from config.settings import Settings, get_settings

from .interfaces import (
    AgentObserverProtocol,
    MCPClientProtocol,
    NullObserver,
)
from .mission_log import MissionLogger
from .mock_client import MockMCPClient
from .planner import SectorPlanner
from .prompts import COMPRESSION_PROMPT, SYSTEM_PROMPT


# ═══════════════════════════════════════════════════════════════════════
#  Mission Orchestrator
# ═══════════════════════════════════════════════════════════════════════


class MissionOrchestrator:
    """
    Primary entry point for all teams.

    Constructor uses dependency injection — the MCP client, settings,
    and observer are all injected.  No external module is ever imported
    internally.

    Args:
        mcp_client: Any object satisfying :class:`MCPClientProtocol`.
        settings: Application settings (auto-loaded if ``None``).
        observer: Optional frontend / API bridge (``NullObserver`` if ``None``).
    """

    def __init__(
        self,
        mcp_client: MCPClientProtocol,
        settings: Settings | None = None,
        observer: AgentObserverProtocol | None = None,
    ) -> None:
        self._mcp = mcp_client
        self._settings = settings or get_settings()
        self._observer = observer or NullObserver()

        # ── internal components ─────────────────────────────────────
        self._logger = MissionLogger(log_dir=self._settings.LOG_DIR)
        self._planner = SectorPlanner(grid_size=self._settings.GRID_SIZE)
        self._llm = self._settings.get_llm()

        # ── build LangGraph agent ───────────────────────────────────
        self._tools = self._build_tools()
        self._agent = create_react_agent(
            model=self._llm,
            tools=self._tools,
            prompt=SYSTEM_PROMPT,
        )

        # ── mission tracking ────────────────────────────────────────
        self._step = 0
        self._survivors_found: list[dict] = []
        self._history_buffer: str = ""

    # ── tool construction ───────────────────────────────────────────

    def _build_tools(self) -> list:
        """
        Wrap each MCPClientProtocol method as a LangChain tool.

        Uses closure over ``self._mcp`` so the tools can call the
        injected MCP client without importing anything.
        """
        mcp = self._mcp
        planner = self._planner
        logger = self._logger
        observer = self._observer
        orchestrator = self

        @langchain_tool
        async def list_active_drones() -> str:
            """List all active drones in the swarm. No input required.
            Returns JSON: {"drones": ["drone_1", ...]}. ALWAYS call this
            first before any other action."""
            result = await mcp.list_active_drones()
            return json.dumps(result)

        @langchain_tool
        async def get_drone_status(drone_id: str) -> str:
            """Get full status of a single drone including battery,
            position, and state. Input: drone_id (string like "drone_1").
            Returns: {"drone_id": str, "battery": int, "x": int, "y": int,
            "state": str}"""
            result = await mcp.get_drone_status(drone_id)
            return json.dumps(dict(result))

        @langchain_tool
        async def move_to(drone_id: str, x: int, y: int) -> str:
            """Move a drone to specific grid coordinates. Use after
            assigning a sector. Input: drone_id, x, y. Returns:
            {"success": bool, "drone_id": str, "x": int, "y": int}.
            ALWAYS call thermal_scan after this."""
            result = await mcp.move_to(drone_id, x, y)
            result_dict = dict(result)
            if result_dict.get("success"):
                planner.mark_scanned(x, y)
            return json.dumps(result_dict)

        @langchain_tool
        async def thermal_scan(drone_id: str) -> str:
            """Run thermal scan at drone's current position to detect
            survivors. Input: drone_id. Returns:
            {"survivor_detected": bool, "confidence": float, "x": int,
            "y": int}. If survivor_detected is true, IMMEDIATELY call
            broadcast_alert."""
            result = await mcp.thermal_scan(drone_id)
            result_dict = dict(result)

            if result_dict.get("survivor_detected"):
                orchestrator._survivors_found.append(result_dict)
                logger.log_survivor(
                    orchestrator._step,
                    result_dict["x"],
                    result_dict["y"],
                    drone_id,
                    result_dict["confidence"],
                )
                observer.on_survivor_found(
                    result_dict["x"],
                    result_dict["y"],
                    result_dict["confidence"],
                )
            return json.dumps(result_dict)

        @langchain_tool
        async def return_to_base(drone_id: str) -> str:
            """Recall a drone to charging base. Use when battery is below
            25%. Input: drone_id. Returns: {"success": bool, "drone_id":
            str, "battery": 100, "state": "charging"}"""
            result = await mcp.return_to_base(drone_id)
            planner.release_sector(drone_id)
            logger.log_battery_event(
                orchestrator._step, drone_id, 0, "recall"
            )
            return json.dumps(result)

        @langchain_tool
        async def get_grid_map() -> str:
            """Get current known state of the full grid — scanned cells
            and found survivors. No input required. Returns:
            {"scanned": [[x,y],...], "survivors": [[x,y],...]}"""
            result = await mcp.get_grid_map()
            return json.dumps(dict(result))

        @langchain_tool
        async def broadcast_alert(x: int, y: int, message: str) -> str:
            """Broadcast a survivor alert to all units and command.
            Input: x, y, message. Call this IMMEDIATELY when thermal_scan
            detects a survivor."""
            result = await mcp.broadcast_alert(x, y, message)
            return json.dumps(result)

        return [
            list_active_drones,
            get_drone_status,
            move_to,
            thermal_scan,
            return_to_base,
            get_grid_map,
            broadcast_alert,
        ]

    # ── battery guardian ────────────────────────────────────────────

    async def _battery_guardian(self, step: int) -> list[str]:
        """
        Autonomous battery monitor — recalls drones below threshold
        WITHOUT LLM involvement.

        Returns:
            List of recalled drone IDs.
        """
        recalled: list[str] = []
        drones_resp = await self._mcp.list_active_drones()

        for drone_id in drones_resp.get("drones", []):
            status = await self._mcp.get_drone_status(drone_id)
            if status["battery"] < self._settings.BATTERY_RECALL_THRESHOLD:
                self._logger.log_battery_event(
                    step, drone_id, status["battery"], "recall"
                )
                await self._mcp.return_to_base(drone_id)
                self._planner.release_sector(drone_id)
                recalled.append(drone_id)

                self._observer.on_tool_call(
                    "return_to_base",
                    {"drone_id": drone_id, "reason": "battery_guardian"},
                    {"recalled": True, "battery_was": status["battery"]},
                )

        return recalled

    # ── context builder ─────────────────────────────────────────────

    def _build_context(self) -> str:
        """
        Assemble current mission context for prompt injection.

        Returns a formatted string appended to the human message.
        """
        planner_report = self._planner.get_status_report()
        survivors_summary = (
            f"{len(self._survivors_found)} survivors found"
            if self._survivors_found
            else "No survivors found yet"
        )

        sector_cov = {
            name: f"{info['coverage']}%"
            for name, info in planner_report["sectors"].items()
        }

        return (
            f"\n\n══ CURRENT MISSION CONTEXT ══\n"
            f"Step: {self._step}\n"
            f"Coverage: {planner_report['overall_coverage']}%\n"
            f"All scanned: {planner_report['all_scanned']}\n"
            f"Drone Assignments: {json.dumps(planner_report['drone_assignments'])}\n"
            f"Sector Coverage: {json.dumps(sector_cov)}\n"
            f"Survivors: {survivors_summary}\n"
        )

    # ── history compression ─────────────────────────────────────────

    async def _compress_history(self, history: str) -> str:
        """Summarise mission history to ≤ 100 words using the LLM."""
        chain = COMPRESSION_PROMPT | self._llm
        result = await chain.ainvoke({"full_history": history})
        return result.content if hasattr(result, "content") else str(result)

    # ── main mission loop ───────────────────────────────────────────

    async def run_mission(
        self,
        objective: str = "Search all sectors for survivors",
        max_steps: int | None = None,
    ) -> dict:
        """
        Execute the full rescue mission.

        Args:
            objective: High-level mission objective text.
            max_steps: Override ``MAX_MISSION_STEPS`` from settings.

        Returns:
            Mission summary dict from :meth:`MissionLogger.get_summary`.
        """
        effective_max_steps = max_steps or self._settings.MAX_MISSION_STEPS

        try:
            # ── pre-mission: battery check ──────────────────────────
            recalled = await self._battery_guardian(0)
            if recalled:
                objective += (
                    f"\n\nNOTE: Drones {recalled} were auto-recalled for low "
                    "battery before mission start."
                )

            # ── build context and run agent ─────────────────────────
            context = self._build_context()
            self._step = 1

            self._logger.log_reasoning(0, f"Mission objective: {objective}")
            self._observer.on_step_start(0, {"objective": objective})

            from .callbacks import ObserverCallbackHandler

            handler = ObserverCallbackHandler(self._observer)
            result = await self._agent.ainvoke(
                {"messages": [HumanMessage(content=objective + context)]},
                config={
                    "recursion_limit": effective_max_steps * 2,
                    "callbacks": [handler],
                },
            )

            # ── extract final output ────────────────────────────────
            if "messages" in result:
                for msg in result["messages"]:
                    if hasattr(msg, "content") and msg.content:
                        self._logger.log_reasoning(
                            self._step, msg.content[:500]
                        )

        except Exception as exc:
            self._logger.log_reasoning(
                self._step,
                f"Mission terminated with error: {type(exc).__name__}: {exc}",
            )
            raise

        finally:
            summary = self._logger.get_summary()
            self._observer.on_mission_complete(summary)
            self._logger.save()

        return summary


# ═══════════════════════════════════════════════════════════════════════
#  Convenience Factory
# ═══════════════════════════════════════════════════════════════════════


def create_agent(
    mcp_client: MCPClientProtocol | None = None,
    use_mock: bool = False,
    **kwargs: Any,
) -> MissionOrchestrator:
    """
    Convenience factory for creating a :class:`MissionOrchestrator`.

    Other teams can do::

        from agent import create_agent

        # Works with no MCP server at all
        agent = create_agent(use_mock=True)

        # Works with the real MCP client
        agent = create_agent(mcp_client=my_client)

    Args:
        mcp_client: An MCP client satisfying :class:`MCPClientProtocol`.
            If ``None`` and ``use_mock`` is ``True``, a :class:`MockMCPClient`
            is created automatically.
        use_mock: If ``True`` (or ``mcp_client`` is ``None``), use
            :class:`MockMCPClient`.
        **kwargs: Forwarded to :class:`MissionOrchestrator` constructor
            (``settings``, ``observer``, etc.).
    """
    if mcp_client is None or use_mock:
        mcp_client = MockMCPClient()

    return MissionOrchestrator(mcp_client=mcp_client, **kwargs)
