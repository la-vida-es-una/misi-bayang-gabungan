/** Shared type definitions matching backend WebSocket event schemas. */

export interface GridInfo {
  width: number;
  height: number;
}

export interface DroneState {
  id: number;
  x: number;
  y: number;
  state: string;
  battery: number;
  visited_cells: number;
  known_survivors: number[];
  known_edges: number;
  target_survivor: number | null;
  llm_waypoint: [number, number] | null;
}

export interface SurvivorState {
  id: number;
  x: number;
  y: number;
  state: "unseen" | "found" | "rescued";
  found_by: number | null;
  rescued_by: number | null;
  found_at_tick: number | null;
  rescued_at_tick: number | null;
}

export interface ObstacleState {
  id: number;
  cells: [number, number][];
  edges: [number, number, number, number][];
}

// ── Per-drone step log (chain of thought) ────────────────────────────

export interface DroneStepLog {
  drone_id: number;
  state_before: string;
  state_after: string;
  pos_before: [number, number];
  pos_after: [number, number];
  battery_before: number;
  battery_after: number;
  visited_count: number;
  known_survivors: number[];
  known_edges_count: number;
  target_survivor: number | null;
  goal: [number, number] | null;
  reasoning: string[];
}

// ── WebSocket Events ────────────────────────────────────────────────

export interface TickEvent {
  type: "tick";
  tick: number;
  drones: DroneState[];
  survivors: SurvivorState[];
  obstacles: ObstacleState[];
  coverage_pct: number;
  base_pos: [number, number];
  grid: GridInfo;
  mission_complete: boolean;
}

export interface MissionStatusEvent {
  type: "mission_status";
  status: "started" | "stopped" | "error";
  message: string;
}

export interface MissionCompleteEvent {
  type: "mission_complete";
  summary: {
    tick: number;
    coverage_pct: number;
    survivors_rescued: number;
    total_survivors: number;
  };
}

export interface SurvivorFoundEvent {
  type: "survivor_found";
  x: number;
  y: number;
  confidence: number;
}

export interface ReasoningEvent {
  type: "reasoning";
  step: number;
  text: string;
}

export interface StepStartEvent {
  type: "step_start";
  step: number;
  context: Record<string, unknown>;
}

export interface ToolCallEvent {
  type: "tool_call";
  tool_name: string;
  params: Record<string, unknown>;
  result: Record<string, unknown>;
}

export interface SimLogEvent {
  type: "sim_log";
  tick: number;
  drone_logs: DroneStepLog[];
}

export type WSEvent =
  | TickEvent
  | MissionStatusEvent
  | MissionCompleteEvent
  | SurvivorFoundEvent
  | ReasoningEvent
  | StepStartEvent
  | ToolCallEvent
  | SimLogEvent;

// ── Context panel message types ─────────────────────────────────────

export interface ContextMessage {
  id: number;
  type: "input" | "reasoning" | "tool_call" | "tool_result";
  text?: string;
  context?: Record<string, unknown>;
  tool_name?: string;
  params?: Record<string, unknown>;
  result?: Record<string, unknown>;
  tick: number;
}

// ── Mission store state ─────────────────────────────────────────────

export interface LogEntry {
  tick: number;
  drone_id: number;
  reasoning: string[];
  state_before: string;
  state_after: string;
  battery: number;
}

export interface MissionState {
  wsStatus: "offline" | "connecting" | "connected";
  running: boolean;
  complete: boolean;
  tick: number;
  coverage: number;
  statusText: string;
  events: string[];
  finalStats: { label: string; value: string }[];
  liveState: TickEvent | null;
  droneTrails: Record<number, { nx: number; ny: number }[]>;
  logs: LogEntry[];
  selectedDroneId: number | null;
  contextMessages: ContextMessage[];
  systemPrompt: string;
  mcpTools: Record<string, unknown>[];
}
