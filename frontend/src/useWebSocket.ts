/**
 * useWebSocket — connects to the backend WS endpoint,
 * dispatches parsed events into the mission store.
 *
 * Handles auto-reconnect on disconnect (3 s interval).
 */

import { useEffect, useRef } from "react";
import { useMissionDispatch } from "./store";
import type { WSEvent } from "./types";
import { logDebug, logError, logInfo, logWarn } from "./logger";

function wsUrl(): string {
  logDebug("useWebSocket.wsUrl", "Resolving websocket URL", {
    host: window.location.host,
    port: window.location.port,
    protocol: window.location.protocol,
  });
  if (window.location.port === "3000") return "ws://localhost:8000/ws";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws`;
}

export function useWebSocket(): void {
  logDebug("useWebSocket", "Hook invoked");
  const dispatch = useMissionDispatch();
  const wsRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    logInfo("useWebSocket", "Effect mounted");
    function connect() {
      logInfo("useWebSocket.connect", "Attempting websocket connection", {
        url: wsUrl(),
      });
      const ws = new WebSocket(wsUrl());
      wsRef.current = ws;
      dispatch({ type: "SET_WS_STATUS", status: "connecting" });

      ws.onopen = () => {
        logInfo("useWebSocket.onopen", "Websocket connected");
        dispatch({ type: "SET_WS_STATUS", status: "connected" });
        if (timerRef.current) {
          clearTimeout(timerRef.current);
          timerRef.current = null;
          logDebug("useWebSocket.onopen", "Reconnect timer cleared");
        }
      };

      ws.onmessage = (e: MessageEvent) => {
        try {
          const event: WSEvent = JSON.parse(e.data);
          logDebug("useWebSocket.onmessage", "Received websocket event", {
            type: event.type,
          });
          dispatch({ type: "WS_EVENT", event });
        } catch (err: unknown) {
          // malformed JSON — skip
          logWarn("useWebSocket.onmessage", "Malformed websocket payload", {
            error: err,
          });
        }
      };

      ws.onclose = () => {
        logWarn("useWebSocket.onclose", "Websocket closed; scheduling reconnect");
        dispatch({ type: "SET_WS_STATUS", status: "offline" });
        timerRef.current = setTimeout(connect, 3000);
      };

      ws.onerror = (e: Event) => {
        logError("useWebSocket.onerror", "Websocket error", e);
        ws.close();
      };
    }

    connect();

    return () => {
      logInfo("useWebSocket", "Effect cleanup");
      if (timerRef.current) clearTimeout(timerRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null; // prevent reconnect on unmount
        wsRef.current.close();
        logInfo("useWebSocket", "Websocket closed on cleanup");
      }
    };
  }, [dispatch]);
}
