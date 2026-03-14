# simulation/

The ground truth engine for Stormwatch SAR. Built on
[Mesa](https://mesa.readthedocs.io/), this package runs the authoritative
simulation of the disaster zone — drone positions, survivor states, obstacle
geometry, and the communication mesh. Everything the MCP server exposes as
tools is backed by this model.

## Files

### `world.py` The Mesa `Model` subclass. Owns the grid, the scheduler, and all
agents. Exposes `step()` to advance the simulation one tick, and `get_state()`
to produce a serializable snapshot for the WebSocket broadcaster.

### `drone_agent.py` The `DroneAgent` Mesa agent. Implements the three-state
FSM:

- **Explore** — steers toward unvisited grid cells, marks coverage, detects
survivors within vision radius, shares findings over the comm mesh
- **Converge** — pursues a known survivor location; switches state on rescue or
battery threshold breach
- **Return** — flies back to base for recharge, then resets and re-enters
Explore

Battery drains each tick. When it falls below the low-battery threshold the
agent overrides its current state and returns regardless.

### `survivor.py` The `SurvivorAgent` Mesa agent. Stationary. Cycles through
three states:

| State | Meaning | 
|---|---| 
| `unseen` | Not yet within any drone's vision radius |
| `found` | Detected — position broadcast across comm mesh | 
|`rescued` | A drone reached the survivor's cell |

Survivor count and positions are randomly generated at world initialisation and
are not known to the drone agents until detected.

### `obstacle.py` The `ObstacleAgent` Mesa agent. Static blocking geometry
placed at world init. Drones sample only the edges of an obstacle that fall
within their vision radius — large obstacles are never fully revealed in a
single pass. Sampled edges are shared over the comm mesh.

### `__init__.py` Package exports: `SARWorld`, `DroneAgent`, `SurvivorAgent`,
`ObstacleAgent`.

## How it fits into the system

``` simulation/          ← this package (ground truth) ↓ mcp_server/tools/    ←
wraps sim calls as MCP tools ↓ agent/orchestrator   ← LLM calls tools via MCP ↓
api/websocket/       ← broadcasts world.get_state() to frontend ```

The simulation never talks directly to the agent or the frontend. All reads and
writes go through the MCP tool layer.

## Running standalone

```bash cd backend pip install -e ".[dev]" python -c " from simulation.world
import SARWorld world = SARWorld(n_drones=5, n_survivors=6, seed=42) for _ in
range(100): world.step() print(world.get_state()) " ```

## Configuration

Parameters passed to `SARWorld`:

| Parameter | Type | Default | Description | 
|---|---|---|---| 
| `n_drones` | int | 5 | Number of drone agents | 
| `n_survivors` | int | 6 | Survivors placed at random free cells |
| `width` | int | 100 | Grid width in cells | | `height` | int | 100 | Grid height in cells | 
| `vision_radius` | float | 8.0 | Drone vision in grid units | 
| `comm_radius` | float | 18.0 | Mesh communication range |
| `battery_drain` | float | 0.9 | Battery lost per tick | 
| `battery_low` | float | 20.0 | Threshold that triggers Return state | 
| `seed`| int \| None | None | Random seed for deterministic runs |
