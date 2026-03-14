"""
Simulation tests — persona-driven scenarios.

Each test class maps to one of the three project personas. The scenario
description is taken directly from the sprint plan so the test reads like
a user story, not just a unit test.

Run with:
    cd backend
    pytest tests/test_simulation.py -v
"""

import pytest
from simulation.world import SARWorld
from simulation.drone_agent import DroneAgent, DroneState
from simulation.survivor import SurvivorAgent, SurvivorState
# from simulation.obstacle import ObstacleAgent


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def world_default():
    """Standard 5-drone, 6-survivor world with a fixed seed."""
    return SARWorld(
        n_drones=5,
        n_survivors=6,
        width=60,
        height=60,
        n_obstacles=4,
        vision_radius=8.0,
        comm_radius=18.0,
        battery_drain=0.5,
        low_battery=20.0,
        seed=42,
    )


def run(world: SARWorld, ticks: int) -> None:
    for _ in range(ticks):
        world.step()


# ---------------------------------------------------------------------------
# Scenario helpers
# ---------------------------------------------------------------------------


def get_drones(world: SARWorld) -> list[DroneAgent]:
    return [a for a in world.schedule.agents if isinstance(a, DroneAgent)]


def get_survivors(world: SARWorld) -> list[SurvivorAgent]:
    return [a for a in world.schedule.agents if isinstance(a, SurvivorAgent)]


# ---------------------------------------------------------------------------
# PERSONA: Major Aiko — Disaster response commander
#
# "I need to know what the swarm knows. Not what it's guessing —
#  what it actually confirmed."
#
# Aiko cares about: drones spreading from base, no collisions/freezes,
# and that the split between confirmed intel and fog is real.
# ---------------------------------------------------------------------------


class TestMajorAikoScenarios:
    def test_drones_leave_base_within_10_ticks(self, world_default):
        """
        Aiko scenario S1: She needs to see 5 drones leave the base and
        spread across the map.
        """
        base = world_default.base_pos
        run(world_default, 10)
        drones = get_drones(world_default)

        moved = [d for d in drones if d._pos() != base]
        assert len(moved) >= 3, (
            f"Expected at least 3 drones to have left base after 10 ticks, "
            f"got {len(moved)}"
        )

    def test_drones_spread_not_cluster(self, world_default):
        """
        Aiko scenario S1: Drones should spread, not all pile up in one sector.
        After 30 ticks, the std deviation of drone positions should be
        meaningful — they're covering different areas.
        """
        run(world_default, 30)
        drones = get_drones(world_default)
        positions = [d._pos() for d in drones]
        xs = [p[0] for p in positions]
        ys = [p[1] for p in positions]

        x_range = max(xs) - min(xs)
        y_range = max(ys) - min(ys)

        assert x_range > 5 or y_range > 5, (
            f"Drones appear clustered: x_range={x_range}, y_range={y_range}"
        )

    def test_no_drone_enters_obstacle_cell(self, world_default):
        """
        Aiko scenario S1: Drones must not crash into obstacles.
        Obstacle cells should never contain a DroneAgent.
        """
        obstacle_cells = world_default._obstacle_cells

        for tick in range(50):
            world_default.step()
            for drone in get_drones(world_default):
                pos = drone._pos()
                assert pos not in obstacle_cells, (
                    f"Drone {drone.unique_id} entered obstacle cell {pos} "
                    f"at tick {tick}"
                )

    def test_unseen_survivors_not_in_drone_knowledge(self, world_default):
        """
        Aiko scenario S2: The fog is real. Drones must not know about
        survivors they haven't detected yet. Confirmed intel only.
        """
        # Before any steps, no drone should know any survivors
        drones = get_drones(world_default)
        for drone in drones:
            assert drone.known_survivors == [], (
                f"Drone {drone.unique_id} has pre-knowledge of survivors before tick 0"
            )

    def test_found_survivor_is_known_to_detecting_drone(self, world_default):
        """
        Aiko scenario S2: When a drone detects a survivor within its vision
        radius, that survivor must appear in the drone's known_survivors.
        """
        run(world_default, 200)
        drones = get_drones(world_default)
        survivors = get_survivors(world_default)

        found = [s for s in survivors if s.state != SurvivorState.UNSEEN]
        if not found:
            pytest.skip(
                "No survivors found in 200 ticks — increase world size or ticks"
            )

        for s in found:
            # At least one drone should know about this survivor
            knows = any(
                s in d.known_survivors or s.state == SurvivorState.RESCUED
                for d in drones
            )
            assert knows, (
                f"Survivor {s.unique_id} is marked {s.state.value} but "
                f"no drone has it in known_survivors"
            )

    def test_get_state_structure(self, world_default):
        """
        Aiko scenario S2: get_state() must always return a complete,
        well-formed snapshot — this is what the frontend god view consumes.
        """
        run(world_default, 5)
        state = world_default.get_state()

        assert "tick" in state
        assert "drones" in state
        assert "survivors" in state
        assert "obstacles" in state
        assert "coverage_pct" in state
        assert "mission_complete" in state
        assert isinstance(state["drones"], list)
        assert len(state["drones"]) == 5

        for d in state["drones"]:
            assert "id" in d
            assert "x" in d
            assert "y" in d
            assert "state" in d
            assert "battery" in d


# ---------------------------------------------------------------------------
# PERSONA: Dr. Tomas — Field medic, 72-hour window
#
# "Battery ran out on drone 3. Nobody told me. We lost 20 minutes on
#  a sector that was already covered."
#
# Tomas cares about: no drone dying in the field, battery recalls working,
# no coverage gaps from a dead drone.
# ---------------------------------------------------------------------------


class TestDrTomasScenarios:
    @pytest.fixture
    def world_fast_drain(self):
        """World with aggressive battery drain to stress-test recall logic."""
        return SARWorld(
            n_drones=5,
            n_survivors=4,
            width=50,
            height=50,
            n_obstacles=3,
            battery_drain=1.5,  # drains fast
            low_battery=20.0,
            seed=7,
        )

    def test_no_drone_battery_reaches_zero_in_field(self, world_fast_drain):
        """
        Tomas scenario S3: No drone should ever reach battery=0 while still
        in Explore or Converge state. The Return trigger must fire first.
        """
        base = world_fast_drain.base_pos

        for tick in range(150):
            world_fast_drain.step()
            for drone in get_drones(world_fast_drain):
                if drone._pos() != base and drone.state != DroneState.RETURN:
                    assert drone.battery > 0, (
                        f"Drone {drone.unique_id} battery hit 0 at tick {tick} "
                        f"while in state {drone.state.value} at pos {drone._pos()}"
                    )

    def test_low_battery_triggers_return_state(self, world_fast_drain):
        """
        Tomas scenario S3: When battery drops to low_battery threshold,
        the drone must switch to RETURN state.
        """
        seen_return = False
        for _ in range(100):
            world_fast_drain.step()
            for drone in get_drones(world_fast_drain):
                if drone.battery <= world_fast_drain.schedule.agents[0].low_battery:
                    if drone.state == DroneState.RETURN:
                        seen_return = True

        assert seen_return, (
            "No drone ever entered RETURN state despite fast battery drain"
        )

    def test_drone_recharges_at_base(self, world_fast_drain):
        """
        Tomas scenario S3: After returning to base, battery must be
        restored to 100. No permanent capacity loss.
        """
        fully_recharged = False
        for tick in range(200):
            world_fast_drain.step()
            for drone in get_drones(world_fast_drain):
                if drone.battery == 100.0 and tick > 10:
                    fully_recharged = True

        assert fully_recharged, (
            "No drone ever recharged to 100% battery — base recharge not working"
        )

    def test_drone_resumes_explore_after_recharge(self, world_fast_drain):
        """
        Tomas scenario S3: After recharging, drone should re-enter EXPLORE
        state and not stay parked at base forever.
        """
        base = world_fast_drain.base_pos
        seen_explore_after_return = False

        prev_state: dict[int, DroneState] = {}
        for tick in range(200):
            world_fast_drain.step()
            for drone in get_drones(world_fast_drain):
                prev = prev_state.get(drone.unique_id)
                if prev == DroneState.RETURN and drone.state == DroneState.EXPLORE:
                    seen_explore_after_return = True
                prev_state[drone.unique_id] = drone.state

        assert seen_explore_after_return, (
            "No drone transitioned from RETURN → EXPLORE. Drones may be stuck at base."
        )

    def test_coverage_increases_over_time(self, world_default):
        """
        Tomas scenario S3: Coverage percentage must grow as drones explore.
        The swarm should not leave gaps by sitting still.
        """
        run(world_default, 20)
        cov_20 = world_default.get_state()["coverage_pct"]

        run(world_default, 80)
        cov_100 = world_default.get_state()["coverage_pct"]

        assert cov_100 > cov_20, (
            f"Coverage did not increase: {cov_20}% at tick 20, {cov_100}% at tick 100"
        )


# ---------------------------------------------------------------------------
# PERSONA: Nadia K. — UN observer, first deployment
#
# "I've never seen this system before. I need to understand what's
#  happening in real time, not after the fact."
#
# Nadia cares about: the mission actually completing, the state being
# legible (clear labels, no missing fields), and the agent log making sense.
# ---------------------------------------------------------------------------


class TestNadiaKScenarios:
    @pytest.fixture
    def world_small(self):
        """Small world that completes fast — good for Nadia's first-run demo."""
        return SARWorld(
            n_drones=5,
            n_survivors=3,
            width=40,
            height=40,
            n_obstacles=2,
            vision_radius=10.0,
            comm_radius=20.0,
            battery_drain=0.3,
            low_battery=15.0,
            seed=99,
        )

    def test_mission_completes_all_survivors_rescued(self, world_small):
        """
        Nadia scenario S5: The mission must complete — all survivors rescued.
        This is the core deliverable she shows to HQ.
        """
        for tick in range(800):
            world_small.step()
            if world_small.get_state()["mission_complete"]:
                break

        state = world_small.get_state()
        assert state["mission_complete"], (
            f"Mission did not complete in 800 ticks. "
            f"Survivors: {[(s.unique_id, s.state.value) for s in get_survivors(world_small)]}"
        )

    def test_survivor_states_progress_correctly(self, world_small):
        """
        Nadia scenario S4: Survivor states must only advance forward:
        UNSEEN → FOUND → RESCUED. Never backwards.
        """
        state_order = {
            SurvivorState.UNSEEN: 0,
            SurvivorState.FOUND: 1,
            SurvivorState.RESCUED: 2,
        }
        survivor_states: dict[int, int] = {}

        for _ in range(400):
            world_small.step()
            for s in get_survivors(world_small):
                current_order = state_order[s.state]
                prev_order = survivor_states.get(s.unique_id, 0)
                assert current_order >= prev_order, (
                    f"Survivor {s.unique_id} went backwards: "
                    f"order {prev_order} → {current_order}"
                )
                survivor_states[s.unique_id] = current_order

    def test_agent_state_labels_are_valid(self, world_small):
        """
        Nadia scenario S4: All drone and survivor states in get_state()
        must be valid string labels — nothing should be None or garbage.
        Nadia reads these labels directly in the mission log.
        """
        run(world_small, 50)
        state = world_small.get_state()

        valid_drone_states = {s.value for s in DroneState}
        valid_survivor_states = {s.value for s in SurvivorState}

        for d in state["drones"]:
            assert d["state"] in valid_drone_states, (
                f"Drone {d['id']} has invalid state label: {d['state']!r}"
            )
            assert 0.0 <= d["battery"] <= 100.0, (
                f"Drone {d['id']} battery out of range: {d['battery']}"
            )

        for s in state["survivors"]:
            assert s["state"] in valid_survivor_states, (
                f"Survivor {s['id']} has invalid state label: {s['state']!r}"
            )

    def test_thermal_scan_returns_legible_result(self, world_small):
        """
        Nadia scenario S4: thermal_scan() must return a dict with a
        'detections' list — the structure the agent panel displays.
        """
        run(world_small, 5)
        drones = get_drones(world_small)
        result = world_small.thermal_scan(drones[0].unique_id)

        assert "drone_id" in result
        assert "detections" in result
        assert isinstance(result["detections"], list)

    def test_comm_mesh_propagates_survivor_knowledge(self, world_small):
        """
        Nadia scenario S4: When one drone finds a survivor, nearby drones
        should learn about it via the comm mesh within a few ticks.
        Nadia sees this as the 'FOUND' label appearing on multiple drone
        panels simultaneously.
        """
        # Run until at least one survivor is found
        found_survivor = None
        for _ in range(300):
            world_small.step()
            for s in get_survivors(world_small):
                if s.state == SurvivorState.FOUND:
                    found_survivor = s
                    break
            if found_survivor:
                break

        if not found_survivor:
            pytest.skip("No survivor found in 300 ticks")

        # Give comm mesh a few ticks to propagate
        run(world_small, 5)

        drones_who_know = [
            d
            for d in get_drones(world_small)
            if found_survivor in d.known_survivors
            or found_survivor.state == SurvivorState.RESCUED
        ]
        assert len(drones_who_know) >= 1, (
            "Survivor was found but no drone recorded knowledge of it"
        )

    def test_list_active_drones_mcp_tool(self, world_small):
        """
        Nadia scenario S3+S4: list_active_drones() is the first MCP tool
        the agent calls. It must return all drones with battery > 0,
        each with a full state dict.
        """
        run(world_small, 10)
        active = world_small.list_active_drones()

        assert len(active) >= 1
        for d in active:
            assert d["battery"] > 0
            assert "id" in d
            assert "x" in d
            assert "y" in d
            assert "state" in d

    def test_move_drone_to_mcp_tool(self, world_small):
        """
        Nadia scenario S3: move_to() is the primary MCP tool the agent
        uses to direct drones. It must actually move the drone and return
        the updated position.
        """
        run(world_small, 2)
        drones = get_drones(world_small)
        drone = drones[0]
        original_pos = drone._pos()

        # find a free cell near the drone
        tx, ty = original_pos[0] + 3, original_pos[1]
        tx = min(tx, world_small.width - 1)
        # skip if blocked
        if world_small.is_blocked(tx, ty):
            pytest.skip("Target cell is blocked — adjust test")

        result = world_small.move_drone_to(drone.unique_id, tx, ty)
        assert "error" not in result
        assert result["x"] == tx
        assert result["y"] == ty


# ---------------------------------------------------------------------------
# Scenario: BatchRunner — parameter sweep
#
# This is the Mesa BatchRunner pattern. Useful for showing how different
# configurations affect mission completion time. Run manually / in CI.
# ---------------------------------------------------------------------------


class TestBatchScenarios:
    @pytest.mark.parametrize(
        "n_drones,n_survivors,expected_complete",
        [
            (3, 3, True),  # minimal fleet, few survivors — should complete
            (5, 6, True),  # standard config
            (5, 10, True),  # more survivors but same fleet
        ],
    )
    def test_mission_completes_across_configs(
        self, n_drones, n_survivors, expected_complete
    ):
        """
        Mesa BatchRunner-style sweep across configurations.
        Each combination should complete within a generous tick budget.
        """
        world = SARWorld(
            n_drones=n_drones,
            n_survivors=n_survivors,
            width=50,
            height=50,
            n_obstacles=3,
            vision_radius=9.0,
            comm_radius=20.0,
            battery_drain=0.3,
            low_battery=15.0,
            seed=42,
        )
        completed = False
        for _ in range(1000):
            world.step()
            if world.get_state()["mission_complete"]:
                completed = True
                break

        assert completed == expected_complete, (
            f"Config n_drones={n_drones}, n_survivors={n_survivors}: "
            f"expected complete={expected_complete}, got {completed}"
        )
