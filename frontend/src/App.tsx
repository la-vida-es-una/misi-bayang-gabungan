/**
 * App — root React component.
 *
 * Three-column layout: DronePanel | SimulationCanvas + HUD | LogPanel
 */

import { useEffect, useState } from "react";
import { useMissionState } from "./store";
import { useWebSocket } from "./useWebSocket";
import { SimulationCanvas } from "./SimulationCanvas";
import { DronePanel } from "./DronePanel";
import { LogPanel } from "./LogPanel";

function apiBase(): string {
  if (window.location.port === "3000") return "http://localhost:8000";
  return "";
}

function useClock(): string {
  const [clock, setClock] = useState("00:00:00");
  useEffect(() => {
    const id = setInterval(() => {
      const ts = Date.now();
      const hh = String(Math.floor((ts / 3600000) % 24)).padStart(2, "0");
      const mm = String(Math.floor((ts / 60000) % 60)).padStart(2, "0");
      const ss = String(Math.floor((ts / 1000) % 60)).padStart(2, "0");
      setClock(`${hh}:${mm}:${ss}`);
    }, 1000);
    return () => clearInterval(id);
  }, []);
  return clock;
}

export function App() {
  useWebSocket();
  const clock = useClock();
  const state = useMissionState();

  async function startMission() {
    try {
      const resp = await fetch(`${apiBase()}/mission/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        console.error("Start failed:", err.detail || "unknown error");
      }
    } catch (e: unknown) {
      console.error("Network error:", e);
    }
  }

  async function stopMission() {
    try {
      await fetch(`${apiBase()}/mission/stop`, { method: "POST" });
    } catch {
      // ignore
    }
  }

  const wsClass =
    state.wsStatus === "connected"
      ? "ws-connected"
      : state.wsStatus === "connecting"
        ? "ws-connecting"
        : "ws-offline";

  return (
    <div id="app-layout">
      {/* Left panel: Drone telemetry + Survivors */}
      <DronePanel />

      {/* Center: Canvas + HUD */}
      <div id="center-col">
        <div id="debrief">
          <SimulationCanvas />

          <div id="hud">
            <div className="corner tl" />
            <div className="corner tr" />
            <div className="corner bl" />
            <div className="corner br" />
            <div id="scan-line" />

            {/* Top bar */}
            <div id="top-bar">
              <div>
                <div className="mission-tag">
                  Live Operations &mdash; MISI BAYANG
                </div>
                <div className="mission-title">
                  SEARCH &amp; RESCUE &mdash; SWARM INTEL DASHBOARD
                </div>
              </div>
              <div className="time-display">{clock}</div>
            </div>

            {/* WS status */}
            <div id="ws-badge" className={wsClass}>
              {state.wsStatus.toUpperCase()}
            </div>

            {/* Event log */}
            <div id="event-log">
              {state.events.map((ev, i) => (
                <div key={i} className="event-item">
                  {ev}
                </div>
              ))}
            </div>

            {/* Result banner */}
            <div
              id="result-banner"
              className={state.complete ? "show" : ""}
            >
              <div className="result-text">Mission Complete</div>
              <div className="result-sub">All survivors extracted</div>
            </div>

            {/* Stats panel */}
            {state.complete && (
              <div id="stats-panel">
                {state.finalStats.map((stat, i) => (
                  <div key={i} className="stat-row">
                    <span className="stat-label">{stat.label}</span>
                    <span className="stat-value">{stat.value}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Status label */}
            <div id="camera-label">
              <div className="cam-tag">Status</div>
              <div className="cam-name">{state.statusText}</div>
            </div>
          </div>

          {/* Controls */}
          <div id="ctrl-bar">
            <button onClick={startMission} disabled={state.running}>
              &#9654; Start Mission
            </button>
            <button onClick={stopMission} disabled={!state.running}>
              &#9632; Stop
            </button>
            <div className="sep" />
            <div id="progress-wrap">
              <div id="progress-bar">
                <div
                  id="progress-fill"
                  style={{ width: `${state.coverage}%` }}
                />
              </div>
              <div id="prog-time">T:{state.tick}</div>
            </div>
            <div id="cov-label">Coverage</div>
          </div>
        </div>
      </div>

      {/* Right panel: Chain of Thought logs */}
      <LogPanel />
    </div>
  );
}
