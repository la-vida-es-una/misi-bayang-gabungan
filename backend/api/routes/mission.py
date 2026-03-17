"""
Mission control REST endpoints.

Provides start/stop controls and status queries for an LLM-driven SAR mission.
The MissionOrchestrator (LangGraph ReAct agent) sets strategic waypoints while
Mesa's autonomous FSM drives drone movement each tick. A concurrent state
broadcaster advances the simulation and pushes world snapshots to the frontend
canvas via WebSocket.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from simulation.drone_agent import DroneAgent
from simulation.world import SARWorld

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mission", tags=["mission"])


# ── request schema ───────────────────────────────────────────────────────────


class MissionConfig(BaseModel):
    """Parameters for a new SAR mission run.  All fields have safe defaults."""

    n_drones: int = 5
    n_survivors: int = 6
    width: int = 20
    height: int = 20
    n_obstacles: int = 0
    vision_radius: float = 3.0
    comm_radius: float = 8.0
    battery_drain: float = 0.5  # FSM drains battery each tick
    low_battery: float = 20.0
    speed: float = 1.0
    tick_interval: float = 0.5  # seconds between state broadcasts
    seed: Optional[int] = None


# ── state broadcaster ────────────────────────────────────────────────────────


async def _state_broadcaster(
    world: SARWorld,
    manager,
    tick_interval: float,
) -> None:
    """Advance the Mesa simulation one tick and broadcast world state.

    This runs concurrently with the LLM orchestrator so the frontend
    canvas updates in real time as drones move autonomously via their FSM.
    """
    logger.info("State broadcaster started | tick_interval=%.3fs", tick_interval)
    try:
        while world.running:
            # Advance simulation — all drone FSMs execute (sense, communicate, move)
            world.step()

            state = world.get_state()
            logger.debug(
                "Broadcast tick | tick=%s | coverage=%s | mission_complete=%s",
                state["tick"],
                state["coverage_pct"],
                state["mission_complete"],
            )
            await manager.broadcast({"type": "tick", **state})

            # Broadcast per-drone FSM reasoning logs
            drone_logs = []
            for agent in world.agents:
                if isinstance(agent, DroneAgent) and agent._last_step_log:
                    drone_logs.append(agent._last_step_log)
            if drone_logs:
                await manager.broadcast({
                    "type": "sim_log",
                    "tick": state["tick"],
                    "drone_logs": drone_logs,
                })

            if state["mission_complete"]:
                rescued = sum(
                    1 for s in state["survivors"] if s["state"] == "rescued"
                )
                await manager.broadcast(
                    {
                        "type": "mission_complete",
                        "summary": {
                            "tick": state["tick"],
                            "coverage_pct": state["coverage_pct"],
                            "survivors_rescued": rescued,
                            "total_survivors": len(state["survivors"]),
                        },
                    }
                )
                break

            await asyncio.sleep(tick_interval)

    except asyncio.CancelledError:
        logger.info("State broadcaster cancelled")
        pass
    except Exception as exc:
        logger.exception("State broadcaster crashed: %s", exc)


# ── orchestrated mission ─────────────────────────────────────────────────────


async def _orchestrated_mission(
    world: SARWorld,
    manager,
    tick_interval: float,
) -> None:
    """Run the LLM-driven mission orchestrator + state broadcaster concurrently."""
    from api.state import app_state
    from agent.real_mcp_client import RealMCPClient
    from agent.orchestrator import MissionOrchestrator
    from api.websocket.observer import WebSocketObserver
    from config.settings import get_settings
    import mcp_server.context as _mcp_ctx
    import mcp_server.server  # noqa: F401 — registers all tool modules on context.mcp

    settings = get_settings()
    logger.info("Orchestrated mission starting")

    # Inject the mission's SARWorld into the MCP server context so that
    # all MCP tools (discovery, movement, sensors, battery) operate on
    # this instance rather than the default module-level singleton.
    _mcp_ctx.set_world(world)

    real_client = RealMCPClient(_mcp_ctx.mcp)
    observer = WebSocketObserver(manager)
    orchestrator = MissionOrchestrator(
        mcp_client=real_client,
        observer=observer,
        settings=settings,
    )
    app_state.orchestrator = orchestrator

    # Start state broadcaster as a concurrent task
    broadcaster = asyncio.create_task(
        _state_broadcaster(world, manager, tick_interval)
    )

    try:
        await orchestrator.run_mission()
    except asyncio.CancelledError:
        logger.info("Orchestrated mission cancelled")
        pass
    except Exception as exc:
        logger.exception("Orchestrator crashed: %s", exc)
        await manager.broadcast(
            {
                "type": "mission_status",
                "status": "error",
                "message": f"LLM agent error: {type(exc).__name__}: {exc}",
            }
        )
    finally:
        logger.info("Orchestrated mission finalizing")
        world.running = False
        broadcaster.cancel()
        try:
            await broadcaster
        except asyncio.CancelledError:
            pass

        # Broadcast final state
        state = world.get_state()
        await manager.broadcast({"type": "tick", **state})

        if state["mission_complete"]:
            rescued = sum(
                1 for s in state["survivors"] if s["state"] == "rescued"
            )
            await manager.broadcast(
                {
                    "type": "mission_complete",
                    "summary": {
                        "tick": state["tick"],
                        "coverage_pct": state["coverage_pct"],
                        "survivors_rescued": rescued,
                        "total_survivors": len(state["survivors"]),
                    },
                }
            )
        else:
            await manager.broadcast(
                {
                    "type": "mission_status",
                    "status": "stopped",
                    "message": "Mission ended",
                }
            )


# ── route handlers ───────────────────────────────────────────────────────────


@router.post("/start")
async def start_mission(config: MissionConfig) -> dict:
    """Create a fresh SARWorld and start the LLM-driven mission.

    If a mission is already running it is cancelled first so the same
    endpoint can be used to restart with new parameters.
    """
    from api.state import app_state

    logger.info(
        "Mission start requested | drones=%d survivors=%d grid=%dx%d obstacles=%d tick=%.3fs seed=%s",
        config.n_drones,
        config.n_survivors,
        config.width,
        config.height,
        config.n_obstacles,
        config.tick_interval,
        config.seed,
    )

    # Cancel any in-flight mission gracefully
    if app_state.mission_task and not app_state.mission_task.done():
        logger.info("Cancelling currently running mission before restart")
        app_state.mission_task.cancel()
        try:
            await app_state.mission_task
        except asyncio.CancelledError:
            pass

    world = SARWorld(
        n_drones=config.n_drones,
        n_survivors=config.n_survivors,
        width=config.width,
        height=config.height,
        n_obstacles=config.n_obstacles,
        vision_radius=config.vision_radius,
        comm_radius=config.comm_radius,
        battery_drain=config.battery_drain,
        low_battery=config.low_battery,
        speed=config.speed,
        seed=config.seed,
    )
    app_state.world = world
    app_state.agent_logs.clear()

    app_state.mission_task = asyncio.create_task(
        _orchestrated_mission(world, app_state.manager, config.tick_interval)
    )
    logger.info("Mission task created")

    await app_state.manager.broadcast(
        {
            "type": "mission_status",
            "status": "started",
            "message": (
                f"Mission started — {config.n_drones} drones, "
                f"{config.n_survivors} survivors, {config.width}x{config.height} grid "
                f"[LLM-driven]"
            ),
        }
    )
    return {"status": "started", "initial_state": world.get_state()}


@router.post("/stop")
async def stop_mission() -> dict:
    """Cancel the running mission."""
    from api.state import app_state

    logger.info("Mission stop requested")

    if app_state.mission_task and not app_state.mission_task.done():
        logger.info("Cancelling active mission task")
        app_state.mission_task.cancel()
        try:
            await app_state.mission_task
        except asyncio.CancelledError:
            pass

    if app_state.world:
        logger.info("Setting world.running=False")
        app_state.world.running = False

    await app_state.manager.broadcast(
        {
            "type": "mission_status",
            "status": "stopped",
            "message": "Mission stopped by operator",
        }
    )
    return {"status": "stopped"}


@router.get("/state")
async def get_state() -> dict:
    """Return a current snapshot of the simulation world."""
    from api.state import app_state

    logger.debug("Mission state requested")

    if not app_state.world:
        raise HTTPException(status_code=404, detail="No active mission")
    return app_state.world.get_state()


@router.get("/drones")
async def get_drones() -> dict:
    """Return the list of all active drones and their status."""
    from api.state import app_state

    logger.debug("Mission drones requested")

    if not app_state.world:
        raise HTTPException(status_code=404, detail="No active mission")
    return {"drones": app_state.world.list_active_drones()}


@router.get("/logs")
async def get_logs(limit: int = 50) -> dict:
    """Return the most recent *limit* buffered agent/tool-call log entries."""
    from api.state import app_state

    logger.debug("Mission logs requested | limit=%d", limit)

    return {"logs": app_state.agent_logs[-limit:]}
