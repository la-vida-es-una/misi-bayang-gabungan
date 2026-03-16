/**
 * LogPanel — scrollable chain-of-thought and reasoning log.
 * Shows LLM reasoning (ARIA) and tool calls alongside drone FSM logs.
 * Filters by selected drone when one is active.
 */

import { useEffect, useRef } from "react";
import { useMissionState } from "./store";

const DRONE_NAMES = [
  "ALPHA",
  "BRAVO",
  "CHARLIE",
  "DELTA",
  "ECHO",
  "FOXTROT",
  "GOLF",
];

function stateColor(s: string): string {
  switch (s) {
    case "explore":
      return "#4fa";
    case "converge":
      return "#fa4";
    case "return":
      return "#f4a";
    case "reasoning":
      return "#4af";
    case "tool_call":
      return "#fa4";
    default:
      return "#4af";
  }
}

function droneName(droneId: number): string {
  if (droneId === -1) return "ARIA";
  return DRONE_NAMES[droneId % DRONE_NAMES.length];
}

function droneColor(droneId: number): string {
  if (droneId === -1) return "#8af";
  return "#4af";
}

export function LogPanel() {
  const { logs, selectedDroneId } = useMissionState();
  const bottomRef = useRef<HTMLDivElement>(null);

  const filtered =
    selectedDroneId !== null
      ? logs.filter((l) => l.drone_id === selectedDroneId)
      : logs;

  // Auto-scroll to bottom on new entries
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [filtered.length]);

  return (
    <div className="panel log-panel">
      <div className="panel-title">
        CHAIN OF THOUGHT
        {selectedDroneId !== null && (
          <span className="filter-badge">
            {" "}
            — {droneName(selectedDroneId)}
          </span>
        )}
      </div>
      <div className="log-scroll">
        {filtered.length === 0 && (
          <div className="panel-empty">Waiting for agent logs...</div>
        )}
        {filtered.map((entry, i) => {
          const isARIA = entry.drone_id === -1;
          const isToolCall = entry.state_after === "tool_call";
          const transitioned = !isARIA && entry.state_before !== entry.state_after;
          const entryClass = isARIA
            ? isToolCall
              ? "log-entry transition"
              : "log-entry"
            : `log-entry ${transitioned ? "transition" : ""}`;
          return (
            <div key={i} className={entryClass}>
              <div className="log-header">
                <span className="log-tick">T:{entry.tick}</span>
                <span
                  className="log-drone"
                  style={{ color: droneColor(entry.drone_id) }}
                >
                  {droneName(entry.drone_id)}
                </span>
                <span
                  className="log-state"
                  style={{ color: stateColor(entry.state_after) }}
                >
                  {entry.state_after.toUpperCase()}
                </span>
                {entry.battery >= 0 && (
                  <span className="log-batt">
                    {entry.battery.toFixed(1)}%
                  </span>
                )}
              </div>
              <div className="log-reasoning">
                {entry.reasoning.map((r, j) => (
                  <div key={j} className="reason-line">
                    {r}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
