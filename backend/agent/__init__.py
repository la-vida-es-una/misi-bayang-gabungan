"""
MISI BAYANG — Agent Package
============================

Autonomous swarm rescue intelligence agent built on LangChain ReAct.
Designed for full decoupling via dependency injection so the agent
works independently of MCP server and simulation implementations.

Quick-start
-----------
::

    # ── Agent team — working independently (no real MCP needed) ────
    from agent import create_agent
    agent = create_agent(use_mock=True)
    result = await agent.run_mission()

    # ── MCP team — when their server is ready ──────────────────────
    from agent import create_agent
    agent = create_agent(mcp_client=their_mcp_client_instance)
    result = await agent.run_mission()

    # ── API team — bridging to frontend ────────────────────────────
    from agent import create_agent, AgentObserverProtocol

    class MyAPIObserver:
        def on_survivor_found(self, x, y, confidence):
            websocket.send({"type": "survivor", "x": x, "y": y})
        def on_step_start(self, step, context): ...
        def on_reasoning(self, step, text): ...
        def on_tool_call(self, tool_name, params, result): ...
        def on_mission_complete(self, summary): ...

    agent = create_agent(mcp_client=real_client, observer=MyAPIObserver())
    result = await agent.run_mission()
"""

from .callbacks import ObserverCallbackHandler
from .interfaces import (
    AgentObserverProtocol,
    MCPClientProtocol,
    NullObserver,
)
from .live_client import LiveMCPClient
from .mission_log import MissionLogger
from .mock_client import MockMCPClient
from .orchestrator import MissionOrchestrator, create_agent
from .planner import SectorPlanner
from .real_mcp_client import RealMCPClient

__all__ = [
    "MissionOrchestrator",
    "create_agent",
    "SectorPlanner",
    "MissionLogger",
    "MCPClientProtocol",
    "AgentObserverProtocol",
    "NullObserver",
    "MockMCPClient",
    "LiveMCPClient",
    "RealMCPClient",
    "ObserverCallbackHandler",
]
