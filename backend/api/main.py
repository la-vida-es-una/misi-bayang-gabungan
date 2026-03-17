"""
MISI BAYANG — FastAPI application entry point.

Starts the HTTP + WebSocket server that bridges the Mesa simulation to the
frontend dashboard.

Run from the ``backend/`` directory::

    uvicorn api.main:app --reload --port 8000

Then open http://localhost:8000 to see the live dashboard.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from api.routes.config import router as config_router
from api.routes.mission import router as mission_router
from api.state import app_state
from config.settings import get_settings
from logging_setup import configure_logging, enable_function_call_tracing

_settings = get_settings()
configure_logging(_settings.LOG_LEVEL)
enable_function_call_tracing(_settings.TRACE_FUNCTION_CALLS)

logger = logging.getLogger(__name__)

# Frontend paths (project root is two levels above backend/api/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_FRONTEND_DIR = _PROJECT_ROOT / "frontend"
_FRONTEND_HTML = _FRONTEND_DIR / "index.html"
_FRONTEND_DIST = _FRONTEND_DIR / "dist"


# ── lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Logging initialized | LOG_LEVEL=%s | TRACE_FUNCTION_CALLS=%s",
        _settings.LOG_LEVEL,
        _settings.TRACE_FUNCTION_CALLS,
    )
    logger.info("MISI BAYANG API ready — dashboard at http://localhost:8000")
    yield
    # Graceful shutdown: cancel any running simulation task
    if app_state.mission_task and not app_state.mission_task.done():
        app_state.mission_task.cancel()
    logger.info("MISI BAYANG API shut down")


# ── app ───────────────────────────────────────────────────────────────────────


app = FastAPI(
    title="MISI BAYANG — SAR Mission Control API",
    description="Real-time decentralised swarm Search & Rescue simulation API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(mission_router)
app.include_router(config_router)

# Mount the frontend dist/ directory for built JS bundles
if _FRONTEND_DIST.is_dir():
    app.mount("/dist", StaticFiles(directory=str(_FRONTEND_DIST)), name="frontend-dist")


# ── routes ────────────────────────────────────────────────────────────────────


@app.get("/context/system-prompt", tags=["context"])
async def get_system_prompt() -> dict:
    """Return the ARIA system prompt used by the LLM agent."""
    from agent.prompts import SYSTEM_PROMPT

    return {"system_prompt": SYSTEM_PROMPT}


@app.get("/context/mcp-tools", tags=["context"])
async def get_mcp_tools() -> dict:
    """Return the registered MCP tool definitions (name, description, parameters)."""
    import mcp_server.context as _mcp_ctx
    import mcp_server.server  # noqa: F401 — ensures tools are registered

    tools = await _mcp_ctx.mcp.list_tools()
    return {
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in tools
        ]
    }


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_dashboard() -> HTMLResponse:
    """Serve the frontend index.html."""
    logger.debug("Dashboard route requested")
    if not _FRONTEND_HTML.exists():
        logger.warning("Dashboard file missing at %s", _FRONTEND_HTML)
        return HTMLResponse(
            "<h1>Dashboard not found</h1>"
            "<p>Run <code>cd frontend && bun install && bun run build</code> first.</p>",
            status_code=404,
        )
    return HTMLResponse(_FRONTEND_HTML.read_text(encoding="utf-8"))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Accept a WebSocket connection and keep it open until disconnect."""
    logger.debug("WebSocket endpoint connect attempt")
    await app_state.manager.connect(websocket)
    try:
        # The server is push-only; we just drain any client pings to keep alive.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await app_state.manager.disconnect(websocket)
