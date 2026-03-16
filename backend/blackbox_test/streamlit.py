from __future__ import annotations

import streamlit as st

from simulation import SARWorld
import mcp_server.context as context

from mcp_server.resources.mission_state import mission_state
from mcp_server.tools.battery import broadcast_alert, return_to_base
from mcp_server.tools.discovery import get_drone_status, list_active_drones
from mcp_server.tools.movement import move_to
from mcp_server.tools.sensors import get_grid_map, thermal_scan
from mcp_server.tools.simulation import step


st.set_page_config(page_title="Misi Bayang Blackbox", layout="wide")
st.title("Misi Bayang Blackbox Console (Streamlit)")


def _init_world() -> None:
    if "world" not in st.session_state:
        st.session_state.world = context.world
    context.world = st.session_state.world


def _reset_world(
    n_drones: int,
    n_survivors: int,
    width: int,
    height: int,
    n_obstacles: int,
    vision_radius: float,
    comm_radius: float,
    battery_drain: float,
    low_battery: float,
    seed: int,
) -> None:
    new_world = SARWorld(
        n_drones=n_drones,
        n_survivors=n_survivors,
        width=width,
        height=height,
        n_obstacles=n_obstacles,
        vision_radius=vision_radius,
        comm_radius=comm_radius,
        battery_drain=battery_drain,
        low_battery=low_battery,
        speed=1.0,
        seed=seed,
    )
    st.session_state.world = new_world
    context.world = new_world


_init_world()

with st.sidebar:
    st.header("World Setup")
    n_drones = st.number_input("Drones", min_value=1, max_value=20, value=5)
    n_survivors = st.number_input("Survivors", min_value=1, max_value=50, value=6)
    width = st.number_input("Grid Width", min_value=10, max_value=200, value=60)
    height = st.number_input("Grid Height", min_value=10, max_value=200, value=60)
    n_obstacles = st.number_input("Obstacles", min_value=0, max_value=30, value=4)
    vision_radius = st.number_input("Vision Radius", min_value=1.0, max_value=50.0, value=8.0)
    comm_radius = st.number_input("Comm Radius", min_value=1.0, max_value=80.0, value=18.0)
    battery_drain = st.number_input("Battery Drain", min_value=0.1, max_value=10.0, value=0.5)
    low_battery = st.number_input("Low Battery Threshold", min_value=1.0, max_value=99.0, value=20.0)
    seed = st.number_input("Seed", min_value=0, max_value=999999, value=42)

    if st.button("Reset World", use_container_width=True):
        _reset_world(
            int(n_drones),
            int(n_survivors),
            int(width),
            int(height),
            int(n_obstacles),
            float(vision_radius),
            float(comm_radius),
            float(battery_drain),
            float(low_battery),
            int(seed),
        )
        st.success("World reset")

active_ids = list_active_drones().get("drones", [])
selected_drone = st.selectbox("Selected Drone", options=active_ids)

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("Simulation")
    ticks = st.number_input("Ticks to step", min_value=1, max_value=500, value=1)
    if st.button("Step", use_container_width=True):
        result = step(int(ticks))
        st.json(result)

with col2:
    st.subheader("Drone Control")
    move_x = st.number_input("Move X", min_value=0, max_value=int(context.world.width - 1), value=0)
    move_y = st.number_input("Move Y", min_value=0, max_value=int(context.world.height - 1), value=0)

    if selected_drone is not None and st.button("Move To", use_container_width=True):
        st.json(move_to(int(selected_drone), int(move_x), int(move_y)))

    if selected_drone is not None and st.button("Thermal Scan", use_container_width=True):
        st.json(thermal_scan(int(selected_drone)))

    if selected_drone is not None and st.button("Return To Base", use_container_width=True):
        st.json(return_to_base(int(selected_drone)))

with col3:
    st.subheader("Alerts")
    alert_x = st.number_input("Alert X", min_value=0, max_value=int(context.world.width - 1), value=0)
    alert_y = st.number_input("Alert Y", min_value=0, max_value=int(context.world.height - 1), value=0)
    alert_msg = st.text_input("Message", value="Survivor spotted")
    if st.button("Broadcast Alert", use_container_width=True):
        st.json(broadcast_alert(int(alert_x), int(alert_y), alert_msg))

st.divider()

state = mission_state()
status_col1, status_col2, status_col3 = st.columns(3)
status_col1.metric("Tick", state["tick"])
status_col2.metric("Coverage %", state["coverage_pct"])
status_col3.metric("Mission Complete", "Yes" if state["mission_complete"] else "No")

st.subheader("Selected Drone Status")
if selected_drone is not None:
    st.json(get_drone_status(int(selected_drone)))
else:
    st.info("No active drones")

st.subheader("Grid Map (Known)")
st.json(get_grid_map())

st.subheader("Mission State")
st.json(state)
