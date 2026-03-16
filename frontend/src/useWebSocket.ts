/**
 * useWebSocket — connects to the backend WS endpoint,
 * dispatches parsed events into the mission store.
 *
 * Handles auto-reconnect on disconnect (3 s interval).
 */

import { useEffect, useRef } from "react";
import { useMissionDispatch } from "./store";
import type { WSEvent } from "./types";

function wsUrl(): string {
  if (window.location.port === "3000") return "ws://localhost:8000/ws";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws`;
}

export function useWebSocket(): void {
  const dispatch = useMissionDispatch();
  const wsRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    function connect() {
      const ws = new WebSocket(wsUrl());
      wsRef.current = ws;
      dispatch({ type: "SET_WS_STATUS", status: "connecting" });

      ws.onopen = () => {
        dispatch({ type: "SET_WS_STATUS", status: "connected" });
        if (timerRef.current) {
          clearTimeout(timerRef.current);
          timerRef.current = null;
        }
      };

      ws.onmessage = (e: MessageEvent) => {
        try {
          const event: WSEvent = JSON.parse(e.data);
          dispatch({ type: "WS_EVENT", event });
        } catch {
          // malformed JSON — skip
        }
      };

      ws.onclose = () => {
        dispatch({ type: "SET_WS_STATUS", status: "offline" });
        timerRef.current = setTimeout(connect, 3000);
      };

      ws.onerror = () => ws.close();
    }

    connect();

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null; // prevent reconnect on unmount
        wsRef.current.close();
      }
    };
  }, [dispatch]);
}
