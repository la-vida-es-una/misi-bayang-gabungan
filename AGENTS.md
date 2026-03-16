# AGENTS.md — Agentic Coding Guide for MISI BAYANG GABUNGAN

> This file provides context and instructions for AI coding agents (GitHub Copilot,
> Claude Code, etc.) working on this repository.

---

## Project Overview

**MISI BAYANG GABUNGAN** is a decentralised swarm search-and-rescue (SAR) simulation
system.  A LangGraph ReAct agent (ARIA) controls a swarm of drones on a 20×20 grid,
using thermal scanning to locate survivors, all without any cloud connectivity
(edge-deployed LLM scenario).

**SDG Alignment**: SDG 3 (Good Health & Well-being) and SDG 9 (Industry, Innovation
& Infrastructure).

---

## Repository Structure

```
misi-bayang-gabungan/
├── backend/                  # Python backend (FastAPI + LangChain + FastMCP)
│   ├── agent/                # LangGraph ReAct agent (ARIA)
│   │   ├── orchestrator.py   # MissionOrchestrator — primary entry point
│   │   ├── prompts.py        # System prompt, ReAct template, compression prompt
│   │   ├── planner.py        # Sector planner (lawnmower waypoints, A–D sectors)
│   │   ├── interfaces.py     # Protocol/TypedDict contracts (MCPClientProtocol, etc.)
│   │   ├── live_client.py    # Live MCP client (calls real MCP server)
│   │   ├── mock_client.py    # MockMCPClient for tests / offline runs
│   │   ├── mission_log.py    # Structured mission logger
│   │   ├── callbacks.py      # LangChain callback handler → AgentObserver bridge
│   │   └── __init__.py       # Exports: MissionOrchestrator, create_agent
│   ├── api/                  # FastAPI HTTP + WebSocket server
│   │   ├── main.py           # App entry point, static file serving, WebSocket
│   │   ├── state.py          # Shared AppState singleton
│   │   ├── routes/
│   │   │   ├── mission.py    # POST /mission/start, POST /mission/stop, GET /mission/status
│   │   │   └── config.py     # GET/POST /config
│   │   └── websocket/        # WebSocket broadcaster for live state pushes
│   ├── mcp_server/           # FastMCP tool server (drone simulation bridge)
│   │   ├── server.py         # FastMCP app definition
│   │   ├── context.py        # mcp + world singletons
│   │   ├── tools/            # MCP tool implementations
│   │   └── resources/        # MCP resources
│   ├── simulation/           # Mesa-based SAR world simulation
│   │   ├── world.py          # SARWorld (Mesa MultiGrid model)
│   │   ├── drone_agent.py    # DroneAgent Mesa agent
│   │   ├── survivor.py       # Survivor agent
│   │   └── obstacle.py       # Obstacle agent
│   ├── config/
│   │   └── settings.py       # Pydantic settings (env vars, LLM factory)
│   ├── tests/                # pytest test suite
│   ├── blackbox_test/        # Blackbox / integration tests
│   └── pyproject.toml        # Python project config (uv)
├── frontend/                 # React + TypeScript dashboard (Bun)
│   ├── src/
│   │   ├── App.tsx           # Root component — three-column layout
│   │   ├── SimulationCanvas.tsx  # Live grid canvas
│   │   ├── DronePanel.tsx    # Left panel: drone telemetry + survivors
│   │   ├── LogPanel.tsx      # Right panel: chain-of-thought logs
│   │   ├── store.ts          # Zustand state store
│   │   └── useWebSocket.ts   # WebSocket hook
│   ├── index.html
│   └── package.json          # Bun project (react 19)
├── docs/
│   ├── api-spec.yaml         # OpenAPI spec
│   └── mcp-spec.json         # MCP tool spec (8 tools)
└── AGENTS.md                 # This file
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Agent framework | LangGraph `create_react_agent` + LangChain tools |
| LLM (cloud) | OpenRouter → `meta-llama/llama-3.1-8b-instruct` (default) |
| LLM (edge) | Ollama (set `USE_LOCAL_LLM=true`) |
| HTTP / WS server | FastAPI + Uvicorn |
| MCP server | FastMCP |
| Simulation | Mesa 3.x (`MultiGrid` model) |
| Backend tooling | `uv`, Python ≥ 3.11, pytest + pytest-asyncio |
| Frontend | React 19, TypeScript, Bun |

---

## How to Run

### Backend

```bash
cd backend

# Install dependencies (first time)
uv sync

# Copy and configure .env
cp .env.example .env
# Set MODEL_KEY, MODEL_NAME, MODEL_BASE_URL (or USE_LOCAL_LLM=true)

# Start the API + MCP server
uvicorn api.main:app --reload --port 8000
```

Then open `http://localhost:8000`.

### Frontend (development)

```bash
cd frontend
bun install
bun run dev       # starts dev server on port 3000
```

### Run tests

```bash
cd backend
uv run pytest tests/ -v
```

---

## Key Environment Variables (`backend/.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_NAME` | `meta-llama/llama-3.1-8b-instruct` | LLM model identifier |
| `MODEL_KEY` | `changeme` | API key for OpenRouter (or Ollama key) |
| `MODEL_BASE_URL` | `https://openrouter.ai/api/v1` | LLM base URL |
| `USE_LOCAL_LLM` | `false` | Set `true` to use Ollama instead |
| `GRID_SIZE` | `20` | Simulation grid dimensions |
| `BATTERY_RECALL_THRESHOLD` | `25` | Battery % below which drones auto-recall |
| `MAX_MISSION_STEPS` | `50` | Max LangGraph recursion steps |
| `TEMPERATURE` | `0.2` | LLM sampling temperature |
| `MAX_TOKENS` | `1024` | Max tokens per LLM response |

---

## Architecture Decisions

### Dependency Injection
`MissionOrchestrator` receives its dependencies via constructor:
- `mcp_client: MCPClientProtocol` — the drone control interface
- `settings: Settings` — config (auto-loaded from env if omitted)
- `observer: AgentObserverProtocol` — optional frontend bridge

**Never** import `mcp_server` from inside `agent/`.  The agent only knows
the `MCPClientProtocol` interface.

### Protocol-Based Contracts
All cross-module contracts are defined as `typing.Protocol` in `agent/interfaces.py`.
Any concrete class that satisfies the structural type is valid — no inheritance required.

### Single LLM Instantiation
`Settings.get_llm()` in `config/settings.py` is the **only** place where a
`ChatOpenAI` or `ChatOllama` instance is created.

### Battery Guardian
Autonomous battery monitoring (`_battery_guardian`) runs **before** each LLM step
and recalls low-battery drones without LLM involvement.

---

## Coding Conventions

### Python (backend)

- **Python ≥ 3.11**; use `from __future__ import annotations` in every module.
- **Type hints everywhere** — `TypedDict` for structured data, `Protocol` for interfaces.
- **Async throughout**: all MCP client methods and agent invocations are `async def`.
- Use `langchain_tool` decorator (from `langchain_core.tools`) to wrap async functions.
- Pydantic `BaseModel` for FastAPI request/response schemas.
- Logging via `logging.getLogger(__name__)` — never `print()` in production code.
- Format docstrings as plain text; module-level docstrings explain the file's purpose.
- Do **not** add new top-level dependencies without updating `pyproject.toml`.

### TypeScript / React (frontend)

- **React 19** functional components only — no class components.
- State management: Zustand (`store.ts`).
- WebSocket connection managed in `useWebSocket.ts` hook.
- CSS lives in `index.html` `<style>` block or co-located `.css` files.
- Build with `bun build`; dev server via `bun run dev`.

---

## MCP Tools (8 tools)

Defined in `docs/mcp-spec.json` and implemented in `mcp_server/tools/`:

| Tool | Description |
|------|-------------|
| `create_drone` | Spawn a drone at a position with battery |
| `get_drones` | List all drones |
| `move_drone` | Move a drone to `[x, y]` |
| `get_simulation_state` | Full grid snapshot |
| `add_victim` | Place a survivor at a position |
| `add_random_victim` | Place a survivor at a random position |
| `handle_rescue` | Drone scans, moves to victim, performs rescue |
| `get_logs` | Retrieve simulation event logs |

The agent-facing tool names (used inside `agent/orchestrator.py`) are slightly
different (`list_active_drones`, `thermal_scan`, etc.) because they wrap the MCP
protocol methods with additional agent-side logic.

---

## Sector Map (20×20 Grid)

```
  Sector C : x=[0..9],  y=[10..19]  (top-left)
  Sector D : x=[10..19], y=[10..19] (top-right)
  ─────────────────────────────────
  Sector A : x=[0..9],  y=[0..9]   (bottom-left)
  Sector B : x=[10..19], y=[0..9]   (bottom-right)
```

Each sector is assigned to one drone.  The planner generates a snake/lawnmower
waypoint pattern covering every cell.  Coverage is tracked per sector; ≥ 95%
per sector = mission complete.

---

## Agent Rules (ARIA must follow)

1. Always call `list_active_drones` first — never assume drone IDs.
2. Write REASONING before every action (ReAct pattern).
3. If battery < 25 %, call `return_to_base` immediately.
4. Never assign two drones to the same sector.
5. After every `move_to`, always call `thermal_scan`.
6. Call `broadcast_alert` immediately when `survivor_detected` is `true`.
7. When all sectors show ≥ 95 % coverage, declare MISSION COMPLETE.

---

## Adding a New MCP Tool

1. Implement the tool function in `mcp_server/tools/` decorated with `@mcp.tool()`.
2. Add the tool signature to `docs/mcp-spec.json`.
3. Add a corresponding method to `MCPClientProtocol` in `agent/interfaces.py`.
4. Implement the method in `agent/live_client.py` and `agent/mock_client.py`.
5. Wrap the method as a `@langchain_tool` in `MissionOrchestrator._build_tools()`.
6. Write a test in `backend/tests/`.

---

## Testing

```bash
# Unit tests
cd backend && uv run pytest tests/ -v

# Specific test file
uv run pytest tests/test_agent.py -v

# Integration tests (requires running backend)
uv run pytest blackbox_test/ -v
```

Tests use `pytest-asyncio` with `asyncio_mode = "auto"` (set in `pyproject.toml`).
Use `MockMCPClient` for agent tests — never the real MCP server.

---

## Common Pitfalls

- **Never** call `get_settings()` inside a module body — only inside functions,
  to avoid loading `.env` at import time during tests.
- The `MissionOrchestrator` is **not** thread-safe; create one instance per mission run.
- LangGraph `recursion_limit` is set to `max_steps * 2` — each tool call counts
  as a step, so the effective agent steps are `max_steps`.
- The frontend expects WebSocket messages at `ws://localhost:8000/ws` in the format
  defined in `api/websocket/`.
