"""
Unit tests for the mcp_server tool functions.

Each test creates a small, deterministic SARWorld (seed=42) and calls the
tool functions directly — no MCP transport layer needed.
"""

from __future__ import annotations

import pytest

from simulation import SARWorld

# ── We need to patch the global `world` in context.py before importing tools ─
# The tools call `world.xxx()` at the module level, so we must replace the
# global before the tool modules are imported.
import mcp_server.context as _ctx


@pytest.fixture(autouse=True)
def small_world():
    """Replace the global simulation world with a tiny deterministic one."""
    original = _ctx.world
    _ctx.world = SARWorld(
        n_drones=2,
        n_survivors=1,
        width=20,
        height=20,
        n_obstacles=0,   # no obstacles — simpler movement
        seed=42,
    )
    yield _ctx.world
    _ctx.world = original


# ── Import tools AFTER fixture has overridden the world ─────────────────────
from mcp_server.tools.discovery import list_active_drones, get_drone_status
from mcp_server.tools.movement import move_to
from mcp_server.tools.sensors import thermal_scan, get_grid_map
from mcp_server.tools.battery import return_to_base, broadcast_alert


# ═══════════════════════════════════════════════════════════════════════════
#  Discovery tool tests
# ═══════════════════════════════════════════════════════════════════════════


class TestListActiveDrones:
    def test_returns_two_drones(self, small_world):
        result = list_active_drones()
        assert "drones" in result
        assert len(result["drones"]) == 2

    def test_drone_ids_are_integers(self, small_world):
        result = list_active_drones()
        for drone_id in result["drones"]:
            assert isinstance(drone_id, int)


class TestGetDroneStatus:
    def test_valid_drone_returns_snapshot(self, small_world):
        drones = list_active_drones()["drones"]
        status = get_drone_status(drones[0])
        assert "id" in status
        assert "battery" in status
        assert "state" in status
        assert "x" in status
        assert "y" in status
        assert status["battery"] == pytest.approx(100.0, abs=1.0)

    def test_invalid_drone_returns_error(self, small_world):
        result = get_drone_status(9999)
        assert "error" in result


# ═══════════════════════════════════════════════════════════════════════════
#  Movement tool tests
# ═══════════════════════════════════════════════════════════════════════════


class TestMoveTo:
    def test_move_returns_new_position(self, small_world):
        drones = list_active_drones()["drones"]
        result = move_to(drones[0], 5, 5)
        assert "error" not in result
        assert result["x"] == 5
        assert result["y"] == 5

    def test_move_invalid_drone_returns_error(self, small_world):
        result = move_to(9999, 5, 5)
        assert "error" in result

    def test_move_clips_to_grid_bounds(self, small_world):
        drones = list_active_drones()["drones"]
        result = move_to(drones[0], 999, 999)  # way out of bounds
        assert "error" not in result
        assert result["x"] < 20
        assert result["y"] < 20


# ═══════════════════════════════════════════════════════════════════════════
#  Sensor tool tests
# ═══════════════════════════════════════════════════════════════════════════


class TestThermalScan:
    def test_scan_returns_expected_keys(self, small_world):
        drones = list_active_drones()["drones"]
        result = thermal_scan(drones[0])
        assert "drone_id" in result
        assert "detections" in result
        assert "survivor_detected" in result
        assert "confidence" in result

    def test_invalid_drone_returns_error(self, small_world):
        result = thermal_scan(9999)
        assert "error" in result

    def test_confidence_zero_when_nothing_detected_far_away(self, small_world):
        """Drone at corner (0,0) with vision_radius=8 — survivor may be elsewhere."""
        drones = list_active_drones()["drones"]
        move_to(drones[0], 0, 0)
        result = thermal_scan(drones[0])
        if not result["survivor_detected"]:
            assert result["confidence"] == 0.0

    def test_high_confidence_when_survivor_at_same_cell(self, small_world):
        """Place drone exactly on the survivor then scan."""
        from simulation import SurvivorAgent
        survivor = next(
            a for a in small_world.agents  # type: ignore[attr-defined]
            if isinstance(a, SurvivorAgent)
        )
        sx, sy = survivor._pos()
        drones = list_active_drones()["drones"]
        move_to(drones[0], sx, sy)
        result = thermal_scan(drones[0])
        assert result["survivor_detected"] is True
        assert result["confidence"] == pytest.approx(0.95)


class TestGetGridMap:
    def test_returns_scanned_and_survivors_keys(self, small_world):
        result = get_grid_map()
        assert "scanned" in result
        assert "survivors" in result

    def test_scanned_cells_are_lists_of_two_ints(self, small_world):
        drones = list_active_drones()["drones"]
        move_to(drones[0], 3, 3)
        result = get_grid_map()
        for cell in result["scanned"]:
            assert len(cell) == 2

    def test_survivors_appear_after_scan(self, small_world):
        from simulation import SurvivorAgent
        survivor = next(
            a for a in small_world.agents  # type: ignore[attr-defined]
            if isinstance(a, SurvivorAgent)
        )
        sx, sy = survivor._pos()
        drones = list_active_drones()["drones"]
        move_to(drones[0], sx, sy)
        thermal_scan(drones[0])
        result = get_grid_map()
        assert [sx, sy] in result["survivors"]


# ═══════════════════════════════════════════════════════════════════════════
#  Battery / emergency tool tests
# ═══════════════════════════════════════════════════════════════════════════


class TestReturnToBase:
    def test_drone_is_at_base_position(self, small_world):
        drones = list_active_drones()["drones"]
        # Move away first
        move_to(drones[0], 15, 15)
        result = return_to_base(drones[0])
        assert result["success"] is True
        bx, by = small_world.base_pos
        assert result["x"] == bx
        assert result["y"] == by

    def test_battery_recharged_to_100(self, small_world):
        drones = list_active_drones()["drones"]
        result = return_to_base(drones[0])
        assert result["battery"] == pytest.approx(100.0)

    def test_invalid_drone_returns_error(self, small_world):
        result = return_to_base(9999)
        assert "error" in result


class TestBroadcastAlert:
    def test_returns_success(self, small_world):
        result = broadcast_alert(5, 5, "Survivor spotted!")
        assert result["success"] is True
        assert result["x"] == 5
        assert result["y"] == 5

    def test_message_echoed_back(self, small_world):
        msg = "Critical: survivor in sector B"
        result = broadcast_alert(10, 10, msg)
        assert result["message"] == msg


# ═══════════════════════════════════════════════════════════════════════════
#  Mission state resource test
# ═══════════════════════════════════════════════════════════════════════════


class TestMissionStateResource:
    def test_get_state_has_required_keys(self, small_world):
        state = small_world.get_state()
        required = {"tick", "drones", "survivors", "obstacles",
                    "coverage_pct", "base_pos", "grid", "mission_complete"}
        assert required.issubset(state.keys())

    def test_grid_dimensions_match(self, small_world):
        state = small_world.get_state()
        assert state["grid"]["width"] == 20
        assert state["grid"]["height"] == 20

    def test_drone_count_matches(self, small_world):
        state = small_world.get_state()
        assert len(state["drones"]) == 2
