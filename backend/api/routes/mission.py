"""
Mission control REST endpoints.

Provides start/stop controls and status queries for an LLM-driven SAR mission.
The MissionOrchestrator (LangGraph ReAct agent) controls all drone movements
via MCP tools — no hardcoded FSM logic. A concurrent state broadcaster pushes
world snapshots to the frontend canvas via WebSocket.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
    battery_drain: float = 0.0  # LLM controls battery via LiveMCPClient
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
    """Periodically broadcast world state to all WebSocket clients.

    This runs concurrently with the LLM orchestrator so the frontend
    canvas updates in real time as drones move.
    """
    try:
        while world.running:
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
                break

            await asyncio.sleep(tick_interval)

    except asyncio.CancelledError:
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
    from agent.live_client import LiveMCPClient
    from agent.orchestrator import MissionOrchestrator
    from api.websocket.observer import WebSocketObserver
    from config.settings import get_settings

    settings = get_settings()

    live_client = LiveMCPClient(world)
    observer = WebSocketObserver(manager)
    orchestrator = MissionOrchestrator(
        mcp_client=live_client,
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

    # Cancel any in-flight mission gracefully
    if app_state.mission_task and not app_state.mission_task.done():
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

    if app_state.mission_task and not app_state.mission_task.done():
        app_state.mission_task.cancel()
        try:
            await app_state.mission_task
        except asyncio.CancelledError:
            pass

    if app_state.world:
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

    if not app_state.world:
        raise HTTPException(status_code=404, detail="No active mission")
    return app_state.world.get_state()


@router.get("/drones")
async def get_drones() -> dict:
    """Return the list of all active drones and their status."""
    from api.state import app_state

    if not app_state.world:
        raise HTTPException(status_code=404, detail="No active mission")
    return {"drones": app_state.world.list_active_drones()}


@router.get("/logs")
async def get_logs(limit: int = 50) -> dict:
    """Return the most recent *limit* buffered agent/tool-call log entries."""
    from api.state import app_state

    return {"logs": app_state.agent_logs[-limit:]}
