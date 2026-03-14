"""
Unit tests for the simulation control tools.
"""

from __future__ import annotations

import pytest
from simulation import SARWorld
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
        n_obstacles=0,
        seed=42,
    )
    yield _ctx.world
    _ctx.world = original

from mcp_server.tools.simulation import step

class TestSimulationStep:
    def test_step_increases_tick(self, small_world):
        initial_tick = small_world.steps
        result = step(ticks=1)
        assert result["success"] is True
        assert result["new_tick"] == initial_tick + 1
        assert small_world.steps == initial_tick + 1

    def test_step_multiple_ticks(self, small_world):
        initial_tick = small_world.steps
        result = step(ticks=5)
        assert result["success"] is True
        assert result["new_tick"] == initial_tick + 5
        assert small_world.steps == initial_tick + 5

    def test_step_default_is_one(self, small_world):
        initial_tick = small_world.steps
        result = step()
        assert result["new_tick"] == initial_tick + 1
