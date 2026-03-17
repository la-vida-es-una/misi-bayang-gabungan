"""
Mission Orchestrator — primary entry point for all teams.

Wires together:
- LangGraph ReAct agent with tool-wrapped MCP protocol methods
- Battery guardian (autonomous recall without LLM)
- Sector planner (waypoint-based coverage)
- Mission logger + observer bridge
- Context builder + history compression

Uses ``langgraph.prebuilt.create_langchain_agent`` (LangChain v1+ API).
"""

from __future__ import annotations

import json
from typing import Any, final

from langchain_core.messages import HumanMessage
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
from .prompts import COMPRESSION_PROMPT, CORRECTION_TEMPLATE, SYSTEM_PROMPT


# ═══════════════════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════════════════

_STEPS_PER_INVOCATION = 10


# ═══════════════════════════════════════════════════════════════════════
#  Mission Orchestrator
# ═══════════════════════════════════════════════════════════════════════


@final
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
            """List all active drones. Returns {"drones": ["drone_1", ...]}."""
            result = await mcp.list_active_drones()
            return json.dumps(result)

        @langchain_tool
        async def get_drone_status(drone_id: str) -> str:
            """Get drone battery, position, state. Input: drone_id.
            Returns {"drone_id", "battery", "x", "y", "state"}."""
            result = await mcp.get_drone_status(drone_id)
            return json.dumps(dict(result))

        @langchain_tool
        async def move_to(drone_id: str, x: int, y: int) -> str:
            """Move drone to waypoint (x,y). Drone navigates at configured
            speed; does NOT teleport. Returns {"success", "drone_id", "x", "y"}."""
            result = await mcp.move_to(drone_id, x, y)
            result_dict = dict(result)
            if result_dict.get("success"):
                planner.mark_scanned(x, y)
            return json.dumps(result_dict)

        @langchain_tool
        async def thermal_scan(drone_id: str) -> str:
            """Thermal scan at drone's current position. Input: drone_id.
            Returns {"survivor_detected", "confidence", "x", "y"}.
            If survivor_detected=true, call broadcast_alert."""
            result = await mcp.thermal_scan(drone_id)
            result_dict = dict(result)

            if result_dict.get("survivor_detected"):
                orchestrator._survivors_found.append(result_dict)
                logger.log_survivor(
                    orchestrator._step,
                    result["x"],
                    result["y"],
                    drone_id,
                    result["confidence"],
                )
                observer.on_survivor_found(
                    result["x"],
                    result["y"],
                    result["confidence"],
                )
            return json.dumps(result_dict)

        @langchain_tool
        async def return_to_base(drone_id: str) -> str:
            """Send drone to recharge. Use when battery<25%. Input: drone_id."""
            result = await mcp.return_to_base(drone_id)
            planner.release_sector(drone_id)
            logger.log_battery_event(orchestrator._step, drone_id, 0, "recall")
            return json.dumps(result)

        @langchain_tool
        async def get_grid_map() -> str:
            """Get scanned cells and found survivors.
            Returns {"scanned": [[x,y],...], "survivors": [[x,y],...]}."""
            result = await mcp.get_grid_map()
            return json.dumps(dict(result))

        @langchain_tool
        async def broadcast_alert(x: int, y: int, message: str) -> str:
            """Broadcast survivor alert. Input: x, y, message."""
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
        return str(result.content) if hasattr(result, "content") else str(result)

    # ── main mission loop ───────────────────────────────────────────

    async def run_mission(
        self,
        objective: str = "Search all sectors for survivors",
        max_steps: int | None = None,
    ) -> dict:
        """
        Execute the full rescue mission.

        Uses an outer verification loop: after each agent invocation,
        checks ground-truth coverage from the SectorPlanner.  If coverage
        is below 95 % and invocation budget remains, re-invokes the agent
        with a corrective message containing actual coverage data.

        Args:
            objective: High-level mission objective text.
            max_steps: Override ``MAX_MISSION_STEPS`` from settings.

        Returns:
            Mission summary dict from :meth:`MissionLogger.get_summary`.
        """
        effective_max_steps = max_steps or self._settings.MAX_MISSION_STEPS

        try:
            self._step = 0
            self._logger.log_reasoning(0, f"Mission objective: {objective}")
            self._observer.on_step_start(0, {"objective": objective})

            from .callbacks import ObserverCallbackHandler

            handler = ObserverCallbackHandler(self._observer)

            for invocation in range(1, effective_max_steps + 1):
                # ── check ground-truth coverage before invoking ────
                if self._planner.all_sectors_scanned():
                    self._logger.log_reasoning(
                        self._step,
                        "Mission complete: all sectors >= 95% coverage.",
                    )
                    break

                # ── build message for this invocation ──────────────
                context = self._build_context()

                if invocation == 1:
                    human_content = objective + context
                else:
                    report = self._planner.get_status_report()
                    correction = CORRECTION_TEMPLATE.format(
                        coverage=report["overall_coverage"],
                        unscanned_sectors=", ".join(
                            self._planner.get_unscanned_sectors()
                        ),
                    )
                    human_content = correction + context

                # ── sync step counter before invocation ────────────
                self._step = handler._step

                # ── invoke the ReAct agent ─────────────────────────
                result = await self._agent.ainvoke(
                    {"messages": [HumanMessage(content=human_content)]},
                    config={
                        "recursion_limit": _STEPS_PER_INVOCATION * 2,
                        "callbacks": [handler],
                    },
                )

                # ── sync step counter after invocation ─────────────
                self._step = handler._step

                # ── check ground-truth coverage after invocation ───
                if self._planner.all_sectors_scanned():
                    self._logger.log_reasoning(
                        self._step,
                        "Mission complete: all sectors >= 95% coverage.",
                    )
                    break

                # ── log continuation ───────────────────────────────
                report = self._planner.get_status_report()
                self._logger.log_reasoning(
                    self._step,
                    f"Invocation {invocation} ended — "
                    f"coverage {report['overall_coverage']}%. "
                    f"Re-invoking agent.",
                )
            else:
                # for-loop exhausted without break — budget spent
                report = self._planner.get_status_report()
                self._logger.log_reasoning(
                    self._step,
                    f"Step budget exhausted ({effective_max_steps} "
                    f"invocations). "
                    f"Final coverage: {report['overall_coverage']}%.",
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
