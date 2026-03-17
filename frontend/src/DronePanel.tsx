/**
 * DronePanel — shows full attribute details for all drones.
 * Clicking a drone selects it for filtered log view.
 */

import { useMissionState, useMissionDispatch } from "./store";
import { logDebug, logInfo } from "./logger";

const DRONE_NAMES = [
  "ALPHA",
  "BRAVO",
  "CHARLIE",
  "DELTA",
  "ECHO",
  "FOXTROT",
  "GOLF",
];
const DRONE_COLORS = [
  "#4af",
  "#f4a",
  "#4fa",
  "#fa4",
  "#a4f",
  "#ff8",
  "#8ff",
];

function stateLabel(s: string): string {
  logDebug("DronePanel.stateLabel", "Compute state label", { state: s });
  switch (s) {
    case "explore":
      return "EXPLORE";
    case "converge":
      return "CONVERGE";
    case "return":
      return "RETURN";
    default:
      return s.toUpperCase();
  }
}

function stateColor(s: string): string {
  logDebug("DronePanel.stateColor", "Compute state color", { state: s });
  switch (s) {
    case "explore":
      return "#4fa";
    case "converge":
      return "#fa4";
    case "return":
      return "#f4a";
    default:
      return "#4af";
  }
}

export function DronePanel() {
  logDebug("DronePanel", "Render start");
  const { liveState, selectedDroneId } = useMissionState();
  const dispatch = useMissionDispatch();

  if (!liveState) {
    logInfo("DronePanel", "No live state available");
    return (
      <div className="panel drone-panel">
        <div className="panel-title">DRONE TELEMETRY</div>
        <div className="panel-empty">No active mission</div>
      </div>
    );
  }

  return (
    <div className="panel drone-panel">
      <div className="panel-title">DRONE TELEMETRY</div>
      <div className="drone-list">
        {liveState.drones.map((d, i) => {
          const name = DRONE_NAMES[i % DRONE_NAMES.length];
          const color = DRONE_COLORS[i % DRONE_COLORS.length];
          const selected = selectedDroneId === d.id;
          return (
            <div
              key={d.id}
              className={`drone-card ${selected ? "selected" : ""}`}
              style={{ borderColor: selected ? color : "rgba(68,170,255,0.15)" }}
              onClick={() =>
                (logInfo("DronePanel", "Drone card clicked", {
                  droneId: d.id,
                  currentlySelected: selected,
                }),
                dispatch({
                  type: "SELECT_DRONE",
                  droneId: selected ? null : d.id,
                }))
              }
            >
              <div className="drone-header">
                <span className="drone-name" style={{ color }}>
                  {name}
                </span>
                <span
                  className="drone-state"
                  style={{ color: stateColor(d.state) }}
                >
                  {stateLabel(d.state)}
                </span>
              </div>
              <div className="drone-attrs">
                <div className="attr-row">
                  <span className="attr-label">POS</span>
                  <span className="attr-value">
                    ({d.x}, {d.y})
                  </span>
                </div>
                <div className="attr-row">
                  <span className="attr-label">BATTERY</span>
                  <span
                    className="attr-value"
                    style={{ color: d.battery < 20 ? "#f44" : "#4af" }}
                  >
                    {d.battery.toFixed(1)}%
                  </span>
                </div>
                <div className="attr-row">
                  <span className="attr-label">VISITED</span>
                  <span className="attr-value">{d.visited_cells} cells</span>
                </div>
                <div className="attr-row">
                  <span className="attr-label">KNOWN SURV</span>
                  <span className="attr-value">
                    {d.known_survivors.length > 0
                      ? d.known_survivors.join(", ")
                      : "none"}
                  </span>
                </div>
                <div className="attr-row">
                  <span className="attr-label">EDGES</span>
                  <span className="attr-value">{d.known_edges}</span>
                </div>
                <div className="attr-row">
                  <span className="attr-label">TARGET</span>
                  <span className="attr-value">
                    {d.target_survivor !== null
                      ? `Survivor #${d.target_survivor}`
                      : "none"}
                  </span>
                </div>
                <div className="attr-row">
                  <span className="attr-label">WAYPOINT</span>
                  <span className="attr-value">
                    {d.llm_waypoint
                      ? `(${d.llm_waypoint[0]}, ${d.llm_waypoint[1]})`
                      : "none"}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Survivor summary */}
      <div className="panel-title" style={{ marginTop: 12 }}>
        SURVIVORS
      </div>
      <div className="survivor-list">
        {liveState.survivors.map((s) => (
          <div key={s.id} className="survivor-row">
            <span className="surv-id">#{s.id}</span>
            <span
              className="surv-state"
              style={{
                color:
                  s.state === "rescued"
                    ? "#4f8"
                    : s.state === "found"
                      ? "#f44"
                      : "#555",
              }}
            >
              {s.state.toUpperCase()}
            </span>
            <span className="surv-pos">
              ({s.x}, {s.y})
            </span>
            {s.found_by !== null && (
              <span className="surv-detail">
                found@T{s.found_at_tick} by D{s.found_by}
              </span>
            )}
            {s.rescued_by !== null && (
              <span className="surv-detail">
                rescued@T{s.rescued_at_tick} by D{s.rescued_by}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
