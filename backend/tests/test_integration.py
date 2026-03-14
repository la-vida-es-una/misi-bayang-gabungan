"""
Integration tests for the real simulation + MCP tool wiring.

These tests validate end-to-end flows across:
- mcp_server.tools.* functions
- shared mcp_server.context.world singleton
- mission://state resource snapshot

Unlike unit tests, each scenario chains multiple tools to verify
cross-module behavior.
"""

from __future__ import annotations

import pytest

from simulation import SARWorld, SurvivorAgent

import mcp_server.context as _ctx
from mcp_server.resources.mission_state import mission_state
from mcp_server.tools.battery import broadcast_alert, return_to_base
from mcp_server.tools.discovery import get_drone_status, list_active_drones
from mcp_server.tools.movement import move_to
from mcp_server.tools.sensors import get_grid_map, thermal_scan
from mcp_server.tools.simulation import step


@pytest.fixture(autouse=True)
def integration_world():
	"""Use a deterministic world for reproducible integration scenarios."""
	original = _ctx.world
	_ctx.world = SARWorld(
		n_drones=2,
		n_survivors=2,
		width=20,
		height=20,
		n_obstacles=0,
		vision_radius=8.0,
		comm_radius=18.0,
		battery_drain=0.3,
		low_battery=20.0,
		seed=42,
	)
	yield _ctx.world
	_ctx.world = original


def test_tool_chain_detects_survivor_and_updates_resource(integration_world):
	"""Discovery → move → scan should propagate into mission://state and grid map."""
	drone_id = list_active_drones()["drones"][0]

	survivor = next(
		agent for agent in integration_world.agents if isinstance(agent, SurvivorAgent)
	)
	sx, sy = survivor._pos()

	moved = move_to(drone_id, sx, sy)
	assert "error" not in moved

	scan = thermal_scan(drone_id)
	assert scan["survivor_detected"] is True
	assert scan["confidence"] == pytest.approx(0.95)

	grid = get_grid_map()
	assert [sx, sy] in grid["survivors"]

	state = mission_state()
	survivor_states = [s["state"] for s in state["survivors"]]
	assert any(s in ("found", "rescued") for s in survivor_states)


def test_return_to_base_then_step_advances_tick(integration_world):
	"""Recall + simulation.step should mutate both drone state and world tick."""
	drone_id = list_active_drones()["drones"][0]

	move_to(drone_id, 10, 10)
	recalled = return_to_base(drone_id)
	assert recalled["success"] is True
	assert recalled["battery"] == pytest.approx(100.0)

	status = get_drone_status(drone_id)
	bx, by = integration_world.base_pos
	assert (status["x"], status["y"]) == (bx, by)

	before = mission_state()["tick"]
	stepped = step(ticks=3)
	after = mission_state()["tick"]
	assert stepped["success"] is True
	assert stepped["new_tick"] == before + 3
	assert after == before + 3


def test_broadcast_alert_persists_in_world(integration_world):
	"""Emergency alert tool should persist structured alert payload in world metadata."""
	result = broadcast_alert(4, 7, "Survivor spotted in Sector A")
	assert result["success"] is True
	assert result["x"] == 4
	assert result["y"] == 7

	assert hasattr(integration_world, "_alerts")
	alert = integration_world._alerts[-1]  # type: ignore[attr-defined]
	assert alert["x"] == 4
	assert alert["y"] == 7
	assert alert["message"] == "Survivor spotted in Sector A"
	assert alert["tick"] == mission_state()["tick"]


def test_full_mission_completion_via_tools(integration_world):
	"""Use only MCP tools to complete a mission and verify mission_complete=True."""
	drone_id = list_active_drones()["drones"][0]

	# Mission resource provides the ground-truth target coordinates.
	for survivor in mission_state()["survivors"]:
		return_to_base(drone_id)
		move_to(drone_id, survivor["x"], survivor["y"])
		thermal_scan(drone_id)

		# Advance until this survivor is rescued (or fail fast if not).
		rescued = False
		for _ in range(8):
			step(ticks=1)
			state = mission_state()
			match = next(s for s in state["survivors"] if s["id"] == survivor["id"])
			if match["state"] == "rescued":
				rescued = True
				break
		assert rescued, f"Survivor {survivor['id']} was not rescued in expected ticks"

	final_state = mission_state()
	assert final_state["mission_complete"] is True
	assert all(s["state"] == "rescued" for s in final_state["survivors"])
