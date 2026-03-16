/**
 * Mission state management via React Context + useReducer.
 */

import {
  createContext,
  useContext,
  useReducer,
  type Dispatch,
  type ReactNode,
} from "react";
import type { MissionState, WSEvent, TickEvent, LogEntry } from "./types";

const MAX_TRAIL = 40;
const MAX_EVENTS = 7;
const MAX_LOGS = 200;

const initialState: MissionState = {
  wsStatus: "offline",
  running: false,
  complete: false,
  tick: 0,
  coverage: 0,
  statusText: "AWAITING MISSION",
  events: [],
  finalStats: [],
  liveState: null,
  droneTrails: {},
  logs: [],
  selectedDroneId: null,
};

// ── Actions ─────────────────────────────────────────────────────────

type Action =
  | { type: "SET_WS_STATUS"; status: MissionState["wsStatus"] }
  | { type: "WS_EVENT"; event: WSEvent }
  | { type: "PUSH_EVENT"; text: string }
  | { type: "SELECT_DRONE"; droneId: number | null }
  | { type: "RESET" };

function pushEvent(events: string[], text: string): string[] {
  return [text, ...events.slice(0, MAX_EVENTS - 1)];
}

function updateTrails(
  trails: Record<number, { nx: number; ny: number }[]>,
  tick: TickEvent,
): Record<number, { nx: number; ny: number }[]> {
  const gw = tick.grid.width;
  const gh = tick.grid.height;
  const next = { ...trails };
  for (const d of tick.drones) {
    const arr = [...(next[d.id] || [])];
    arr.push({ nx: d.x / (gw - 1), ny: 1 - d.y / (gh - 1) });
    if (arr.length > MAX_TRAIL) arr.shift();
    next[d.id] = arr;
  }
  return next;
}

// ── Reducer ─────────────────────────────────────────────────────────

function missionReducer(state: MissionState, action: Action): MissionState {
  switch (action.type) {
    case "SET_WS_STATUS":
      return { ...state, wsStatus: action.status };

    case "PUSH_EVENT":
      return { ...state, events: pushEvent(state.events, action.text) };

    case "SELECT_DRONE":
      return { ...state, selectedDroneId: action.droneId };

    case "RESET":
      return { ...initialState };

    case "WS_EVENT": {
      const ev = action.event;
      switch (ev.type) {
        case "tick":
          return {
            ...state,
            tick: ev.tick,
            coverage: ev.coverage_pct,
            statusText: `LIVE \u2014 TICK ${ev.tick}`,
            liveState: ev,
            droneTrails: updateTrails(state.droneTrails, ev),
          };

        case "sim_log": {
          const newLogs: LogEntry[] = ev.drone_logs.map((dl) => ({
            tick: ev.tick,
            drone_id: dl.drone_id,
            reasoning: dl.reasoning,
            state_before: dl.state_before,
            state_after: dl.state_after,
            battery: dl.battery_after,
          }));
          const merged = [...state.logs, ...newLogs];
          return {
            ...state,
            logs: merged.length > MAX_LOGS ? merged.slice(-MAX_LOGS) : merged,
          };
        }

        case "mission_status": {
          if (ev.status === "started") {
            return {
              ...state,
              running: true,
              complete: false,
              tick: 0,
              coverage: 0,
              events: pushEvent([], ev.message),
              finalStats: [],
              statusText: "MISSION ACTIVE",
              liveState: null,
              droneTrails: {},
              logs: [],
              selectedDroneId: null,
            };
          }
          if (ev.status === "stopped" || ev.status === "error") {
            return {
              ...state,
              running: false,
              statusText: "MISSION HALTED",
              events: pushEvent(state.events, ev.message),
            };
          }
          return { ...state, events: pushEvent(state.events, ev.message) };
        }

        case "mission_complete":
          return {
            ...state,
            running: false,
            complete: true,
            statusText: "MISSION COMPLETE",
            events: pushEvent(
              state.events,
              "All survivors rescued \u2014 Mission Complete",
            ),
            finalStats: [
              {
                label: "Survivors rescued",
                value: `${ev.summary.survivors_rescued} / ${ev.summary.total_survivors}`,
              },
              { label: "Coverage", value: `${ev.summary.coverage_pct}%` },
              { label: "Ticks elapsed", value: String(ev.summary.tick) },
            ],
          };

        case "survivor_found":
          return {
            ...state,
            events: pushEvent(
              state.events,
              `Survivor at (${ev.x}, ${ev.y}) \u2014 ${(ev.confidence * 100).toFixed(0)}% conf`,
            ),
          };

        case "reasoning": {
          const reasoningLog: LogEntry = {
            tick: state.tick,
            drone_id: -1,
            reasoning: [ev.text],
            state_before: "reasoning",
            state_after: "reasoning",
            battery: -1,
          };
          const rLogs = [...state.logs, reasoningLog];
          return {
            ...state,
            events: pushEvent(
              state.events,
              "AI: " + ev.text.substring(0, 70),
            ),
            logs: rLogs.length > MAX_LOGS ? rLogs.slice(-MAX_LOGS) : rLogs,
          };
        }

        case "tool_call": {
          const toolLog: LogEntry = {
            tick: state.tick,
            drone_id: -1,
            reasoning: [
              `[TOOL] ${ev.tool_name}(${JSON.stringify(ev.params)})`,
              `=> ${JSON.stringify(ev.result).substring(0, 200)}`,
            ],
            state_before: "tool_call",
            state_after: "tool_call",
            battery: -1,
          };
          const tLogs = [...state.logs, toolLog];
          return {
            ...state,
            events: pushEvent(
              state.events,
              `TOOL: ${ev.tool_name}`,
            ),
            logs: tLogs.length > MAX_LOGS ? tLogs.slice(-MAX_LOGS) : tLogs,
          };
        }

        default:
          return state;
      }
    }

    default:
      return state;
  }
}

// ── Context ─────────────────────────────────────────────────────────

const MissionStateCtx = createContext<MissionState>(initialState);
const MissionDispatchCtx = createContext<Dispatch<Action>>(() => {});

export function MissionProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(missionReducer, initialState);
  return (
    <MissionStateCtx.Provider value={state}>
      <MissionDispatchCtx.Provider value={dispatch}>
        {children}
      </MissionDispatchCtx.Provider>
    </MissionStateCtx.Provider>
  );
}

export function useMissionState(): MissionState {
  return useContext(MissionStateCtx);
}

export function useMissionDispatch(): Dispatch<Action> {
  return useContext(MissionDispatchCtx);
}
