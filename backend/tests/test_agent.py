"""
Test suite for the MISI BAYANG agent package.

Uses pytest + pytest-asyncio. All async tests use MockMCPClient(seed=42)
for deterministic, reproducible scenarios.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Imports under test ──────────────────────────────────────────────
from agent.interfaces import (
    AgentObserverProtocol,
    MCPClientProtocol,
    NullObserver,
)
from agent.mission_log import MissionLogger
from agent.mock_client import MockMCPClient
from agent.orchestrator import MissionOrchestrator, create_agent
from agent.planner import SectorPlanner
from config.settings import Settings


# ═══════════════════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_settings() -> Settings:
    """Test settings with safe defaults."""
    return Settings(
        MODEL_NAME="test-model",
        MODEL_KEY="test-key",
        MODEL_BASE_URL="https://test.example.com/v1",
        USE_LOCAL_LLM=False,
        GRID_SIZE=20,
        BATTERY_RECALL_THRESHOLD=25,
        MAX_MISSION_STEPS=5,
        LOG_DIR="test_logs",
        TEMPERATURE=0.0,
        MAX_TOKENS=256,
        NUM_CTX=1024,
    )


@pytest.fixture
def mock_mcp() -> MockMCPClient:
    """Deterministic mock MCP client with seed=42."""
    return MockMCPClient(seed=42)


MOCK_LLM_RESPONSE = """\
Thought: I need to discover available drones before planning anything.
Drone_1 has 80% battery. Assigning to Sector A for initial sweep.
Action: move_to
Action Input: {"drone_id": "drone_1", "x": 2, "y": 2}
"""


# ═══════════════════════════════════════════════════════════════════════
#  Interface / Protocol conformance tests
# ═══════════════════════════════════════════════════════════════════════


class TestProtocolConformance:
    """Verify that mock and null implementations satisfy their protocols."""

    def test_mock_client_satisfies_protocol(self) -> None:
        """MockMCPClient must fully satisfy MCPClientProtocol."""
        client = MockMCPClient(seed=42)
        assert isinstance(client, MCPClientProtocol)

    def test_null_observer_satisfies_protocol(self) -> None:
        """NullObserver must satisfy AgentObserverProtocol with no errors."""
        observer = NullObserver()
        assert isinstance(observer, AgentObserverProtocol)

        # Calling every method should not raise
        observer.on_step_start(1, {})
        observer.on_reasoning(1, "test")
        observer.on_tool_call("test", {}, {})
        observer.on_survivor_found(0, 0, 0.9)
        observer.on_mission_complete({})


# ═══════════════════════════════════════════════════════════════════════
#  MockMCPClient tests
# ═══════════════════════════════════════════════════════════════════════


class TestMockMCPClient:
    """Test simulated world behaviour of MockMCPClient."""

    @pytest.mark.asyncio
    async def test_mock_client_returns_5_drones(self, mock_mcp: MockMCPClient) -> None:
        """list_active_drones() should return exactly 5 drones."""
        result = await mock_mcp.list_active_drones()
        assert len(result["drones"]) == 5
        assert all(d.startswith("drone_") for d in result["drones"])

    @pytest.mark.asyncio
    async def test_mock_client_battery_drains_on_move(self, mock_mcp: MockMCPClient) -> None:
        """Battery should decrease by 3% per move_to call (total 9% for 3 moves)."""
        status_before = await mock_mcp.get_drone_status("drone_1")
        initial_battery = status_before["battery"]

        for i in range(3):
            await mock_mcp.move_to("drone_1", i, i)

        status_after = await mock_mcp.get_drone_status("drone_1")
        expected = initial_battery - 9
        assert status_after["battery"] == expected

    @pytest.mark.asyncio
    async def test_mock_client_survivor_detection_within_range(
        self, mock_mcp: MockMCPClient
    ) -> None:
        """Drone adjacent to a survivor should detect it in thermal scan."""
        world = mock_mcp.get_world_state()
        survivor_coords = world["survivors"]
        assert len(survivor_coords) > 0

        # Place drone at first survivor's location
        sx, sy = survivor_coords[0]
        await mock_mcp.move_to("drone_1", sx, sy)
        scan = await mock_mcp.thermal_scan("drone_1")

        assert scan["survivor_detected"] is True
        assert 0.85 <= scan["confidence"] <= 0.99

    @pytest.mark.asyncio
    async def test_mock_client_reproducible_with_seed(self) -> None:
        """Two MockMCPClient(seed=42) instances must produce identical state."""
        client_a = MockMCPClient(seed=42)
        client_b = MockMCPClient(seed=42)

        state_a = client_a.get_world_state()
        state_b = client_b.get_world_state()

        # Compare drone positions
        for did in state_a["drones"]:
            da = state_a["drones"][did]
            db = state_b["drones"][did]
            assert da["x"] == db["x"]
            assert da["y"] == db["y"]
            assert da["battery"] == db["battery"]

        # Compare survivor positions
        assert state_a["survivors"] == state_b["survivors"]

    @pytest.mark.asyncio
    async def test_mock_client_reset(self, mock_mcp: MockMCPClient) -> None:
        """After moves + reset, world state should return to initial."""
        initial_state = mock_mcp.get_world_state()

        # Perform some actions
        await mock_mcp.move_to("drone_1", 5, 5)
        await mock_mcp.move_to("drone_2", 10, 10)

        # State should have changed
        mid_state = mock_mcp.get_world_state()
        assert len(mid_state["scanned_coords"]) > 0

        # Reset
        mock_mcp.reset(seed=42)
        reset_state = mock_mcp.get_world_state()

        # Drones should be back to original positions
        for did in initial_state["drones"]:
            assert (
                reset_state["drones"][did]["x"] == initial_state["drones"][did]["x"]
            )
            assert (
                reset_state["drones"][did]["y"] == initial_state["drones"][did]["y"]
            )
        assert len(reset_state["scanned_coords"]) == 0

    @pytest.mark.asyncio
    async def test_mock_client_return_to_base_recharges(self, mock_mcp: MockMCPClient) -> None:
        """return_to_base should recharge drone to 100%."""
        mock_mcp.inject_low_battery("drone_1")
        status = await mock_mcp.get_drone_status("drone_1")
        assert status["battery"] == 15

        await mock_mcp.return_to_base("drone_1")
        status = await mock_mcp.get_drone_status("drone_1")
        assert status["battery"] == 100

    @pytest.mark.asyncio
    async def test_mock_client_broadcast_alert(self, mock_mcp: MockMCPClient) -> None:
        """broadcast_alert should return success."""
        result = await mock_mcp.broadcast_alert(5, 5, "Test alert")
        assert result["success"] is True
        assert result["x"] == 5
        assert result["y"] == 5

    @pytest.mark.asyncio
    async def test_mock_client_grid_map(self, mock_mcp: MockMCPClient) -> None:
        """get_grid_map should track scanned coords."""
        await mock_mcp.move_to("drone_1", 3, 3)
        grid = await mock_mcp.get_grid_map()
        assert [3, 3] in grid["scanned"]


# ═══════════════════════════════════════════════════════════════════════
#  SectorPlanner tests
# ═══════════════════════════════════════════════════════════════════════


class TestSectorPlanner:
    """Test sector assignment, waypoints, and coverage tracking."""

    def test_planner_assign_no_duplicates(self) -> None:
        """Assigning 5 drones — 4 should get sectors, 5th returns None."""
        planner = SectorPlanner(grid_size=20)
        assignments = []
        for i in range(1, 6):
            sector = planner.assign_sector(f"drone_{i}")
            assignments.append(sector)

        assert assignments[:4] == ["A", "B", "C", "D"]
        assert assignments[4] is None

    def test_planner_release_and_reassign(self) -> None:
        """Release a sector and another drone should be able to take it."""
        planner = SectorPlanner(grid_size=20)

        sector = planner.assign_sector("drone_1")
        assert sector == "A"

        planner.release_sector("drone_1")
        assert planner.get_drone_assignment("drone_1") is None

        sector = planner.assign_sector("drone_2")
        assert sector == "A"  # Gets the released sector

    def test_planner_lawnmower_full_coverage(self) -> None:
        """Waypoints for a sector should cover all cells with no duplicates."""
        planner = SectorPlanner(grid_size=20)
        waypoints = planner.get_next_waypoints("A")

        # Sector A is 10×10 = 100 cells
        assert len(waypoints) == 100
        assert len(set(waypoints)) == 100  # No duplicates

        # All within sector A bounds
        for x, y in waypoints:
            assert 0 <= x <= 9
            assert 0 <= y <= 9

    def test_planner_coverage_percent(self) -> None:
        """Marking 200 out of 400 cells should give 50% coverage."""
        planner = SectorPlanner(grid_size=20)

        count = 0
        for x in range(20):
            for y in range(10):
                planner.mark_scanned(x, y)
                count += 1

        assert count == 200
        assert abs(planner.coverage_percent() - 0.5) < 0.01

    def test_planner_all_sectors_scanned(self) -> None:
        """all_sectors_scanned() should be True when coverage >= 95%."""
        planner = SectorPlanner(grid_size=20)
        assert planner.all_sectors_scanned() is False

        # Mark all cells
        for x in range(20):
            for y in range(20):
                planner.mark_scanned(x, y)

        assert planner.all_sectors_scanned() is True

    def test_planner_get_next_waypoint_advances(self) -> None:
        """get_next_waypoint should advance through the plan sequentially."""
        planner = SectorPlanner(grid_size=20)
        planner.assign_sector("drone_1")

        wp1 = planner.get_next_waypoint("drone_1")
        wp2 = planner.get_next_waypoint("drone_1")
        assert wp1 is not None
        assert wp2 is not None
        assert wp1 != wp2

    def test_planner_status_report(self) -> None:
        """get_status_report() should return a well-structured dict."""
        planner = SectorPlanner(grid_size=20)
        planner.assign_sector("drone_1")

        report = planner.get_status_report()
        assert "overall_coverage" in report
        assert "sectors" in report
        assert "drone_assignments" in report
        assert report["drone_assignments"]["drone_1"] == "A"


# ═══════════════════════════════════════════════════════════════════════
#  MissionLogger tests
# ═══════════════════════════════════════════════════════════════════════


class TestMissionLogger:
    """Test event logging and file persistence."""

    def test_logger_all_event_types(self, tmp_path: Path) -> None:
        """Log one of each event type and check summary counts."""
        logger = MissionLogger(log_dir=str(tmp_path))

        logger.log_reasoning(1, "Thinking about next move")
        logger.log_tool_call(1, "move_to", {"drone_id": "d1", "x": 5, "y": 5})
        logger.log_survivor(2, 5, 5, "d1", 0.95)
        logger.log_battery_event(3, "d2", 20, "recall")

        summary = logger.get_summary()
        assert summary["reasoning_count"] == 1
        assert summary["tool_calls_made"] == 1
        assert summary["survivors_found"] == 1
        assert summary["battery_events"] == 1
        assert summary["total_steps"] == 3

    def test_logger_save_both_files(self, tmp_path: Path) -> None:
        """save() should create both .json and .txt files."""
        logger = MissionLogger(log_dir=str(tmp_path))

        logger.log_reasoning(1, "Test reasoning")
        logger.log_tool_call(1, "test_tool", {"key": "value"}, {"result": "ok"})

        json_path, txt_path = logger.save(log_dir=tmp_path)

        assert json_path.exists()
        assert txt_path.exists()
        assert json_path.suffix == ".json"
        assert txt_path.suffix == ".txt"

        # Verify JSON is valid
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert "summary" in data
        assert "reasoning" in data
        assert "tool_calls" in data

        # Verify TXT contains header
        txt_content = txt_path.read_text(encoding="utf-8")
        assert "MISI BAYANG" in txt_content


# ═══════════════════════════════════════════════════════════════════════
#  Orchestrator tests
# ═══════════════════════════════════════════════════════════════════════


class TestOrchestrator:
    """Test orchestrator construction, battery guardian, and mission run."""

    def test_create_agent_with_mock(self) -> None:
        """create_agent(use_mock=True) should return MissionOrchestrator."""
        with patch("agent.orchestrator.get_settings") as mock_get:
            mock_get.return_value = Settings(
                MODEL_NAME="test", MODEL_KEY="test",
                USE_LOCAL_LLM=False, MODEL_BASE_URL="https://test.example.com/v1",
            )
            with patch("agent.orchestrator.create_react_agent") as mock_react:
                mock_react.return_value = MagicMock()
                agent = create_agent(use_mock=True)
                assert isinstance(agent, MissionOrchestrator)

    def test_create_agent_with_injected_client(self, mock_mcp: MockMCPClient) -> None:
        """create_agent(mcp_client=...) should accept any protocol-conforming object."""
        with patch("agent.orchestrator.get_settings") as mock_get:
            mock_get.return_value = Settings(
                MODEL_NAME="test", MODEL_KEY="test",
                USE_LOCAL_LLM=False, MODEL_BASE_URL="https://test.example.com/v1",
            )
            with patch("agent.orchestrator.create_react_agent") as mock_react:
                mock_react.return_value = MagicMock()
                agent = create_agent(mcp_client=mock_mcp)
                assert isinstance(agent, MissionOrchestrator)

    @pytest.mark.asyncio
    async def test_battery_guardian_recalls_low_drone(
        self, mock_mcp: MockMCPClient, mock_settings: Settings
    ) -> None:
        """Battery guardian should recall drones below threshold."""
        mock_mcp.inject_low_battery("drone_1")

        with patch("agent.orchestrator.create_react_agent") as mock_react:
            mock_react.return_value = MagicMock()
            orchestrator = MissionOrchestrator(
                mcp_client=mock_mcp,
                settings=mock_settings,
            )

        recalled = await orchestrator._battery_guardian(step=1)
        assert "drone_1" in recalled

    @pytest.mark.asyncio
    async def test_battery_guardian_no_false_recalls(
        self, mock_mcp: MockMCPClient, mock_settings: Settings
    ) -> None:
        """No drone should be recalled if all batteries are above threshold."""
        with patch("agent.orchestrator.create_react_agent") as mock_react:
            mock_react.return_value = MagicMock()
            orchestrator = MissionOrchestrator(
                mcp_client=mock_mcp,
                settings=mock_settings,
            )

        recalled = await orchestrator._battery_guardian(step=1)
        assert recalled == []

    @pytest.mark.asyncio
    async def test_run_mission_completes(
        self,
        mock_mcp: MockMCPClient,
        mock_settings: Settings,
        tmp_path: Path,
    ) -> None:
        """
        Run mission with mocked LLM agent. Should complete and return
        summary dict with expected keys.
        """
        mock_settings_local = Settings(
            MODEL_NAME="test",
            MODEL_KEY="test",
            USE_LOCAL_LLM=False,
            MODEL_BASE_URL="https://test.example.com/v1",
            MAX_MISSION_STEPS=3,
            LOG_DIR=str(tmp_path),
        )

        with patch("agent.orchestrator.create_react_agent") as mock_react:
            mock_react.return_value = MagicMock()

            orchestrator = MissionOrchestrator(
                mcp_client=mock_mcp,
                settings=mock_settings_local,
            )

        # Mock the agent graph to return a predetermined result
        mock_msg = MagicMock()
        mock_msg.content = "Mission complete — 2 survivors found."
        mock_result = {"messages": [mock_msg]}

        orchestrator._agent = MagicMock()
        orchestrator._agent.ainvoke = AsyncMock(return_value=mock_result)

        summary = await orchestrator.run_mission(max_steps=3)

        assert isinstance(summary, dict)
        assert "total_steps" in summary
        assert "survivors_found" in summary
        assert "tool_calls_made" in summary

        # Check log files were saved
        log_files = list(tmp_path.glob("mission_*.json"))
        assert len(log_files) >= 1
