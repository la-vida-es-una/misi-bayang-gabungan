/**
 * ContextPanel — accordion-based context viewer replacing the old LogPanel.
 * Shows three sections: System Prompt, Message History, and MCP Tools.
 */

import { useEffect, useRef, useState } from "react";
import { useMissionState, useMissionDispatch } from "./store";
import type { ContextMessage } from "./types";

function apiBase(): string {
  if (window.location.port === "3000") return "http://localhost:8000";
  return "";
}

// ── Accordion wrapper ────────────────────────────────────────────────

function Accordion({
  title,
  badge,
  defaultOpen,
  children,
}: {
  title: string;
  badge?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen ?? false);

  return (
    <div className="accordion">
      <button
        className={`accordion-header ${open ? "open" : ""}`}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="accordion-chevron">{open ? "\u25BE" : "\u25B8"}</span>
        <span className="accordion-title">{title}</span>
        {badge && <span className="accordion-badge">{badge}</span>}
      </button>
      {open && <div className="accordion-body">{children}</div>}
    </div>
  );
}

// ── Message summary line ─────────────────────────────────────────────

function msgIcon(type: ContextMessage["type"]): string {
  switch (type) {
    case "input":
      return "\ud83d\udcdd";
    case "reasoning":
      return "\ud83e\udd16";
    case "tool_call":
      return "\u2699\ufe0f";
    case "tool_result":
      return "\ud83d\udce6";
  }
}

function msgLabel(msg: ContextMessage): string {
  switch (msg.type) {
    case "input":
      return `Input: ${msg.text ?? ""}`;
    case "reasoning":
      return `Assistant: ${msg.text ?? ""}`;
    case "tool_call":
      return `Tool call: ${msg.tool_name}(${JSON.stringify(msg.params ?? {})})`;
    case "tool_result":
      return `Tool result: ${msg.tool_name} \u2192 ${JSON.stringify(msg.result ?? {})}`;
  }
}

function msgFull(msg: ContextMessage): string {
  switch (msg.type) {
    case "input":
      return JSON.stringify(msg.context ?? {}, null, 2);
    case "reasoning":
      return msg.text ?? "";
    case "tool_call":
      return JSON.stringify(msg.params ?? {}, null, 2);
    case "tool_result":
      return JSON.stringify(msg.result ?? {}, null, 2);
  }
}

function MessageItem({ msg }: { msg: ContextMessage }) {
  const [expanded, setExpanded] = useState(false);
  const summary = msgLabel(msg);
  const truncated =
    summary.length > 70 ? summary.substring(0, 70) + " ..." : summary;

  return (
    <div className={`msg-item ${expanded ? "expanded" : ""}`}>
      <div className="msg-summary" onClick={() => setExpanded((e) => !e)}>
        <span className="msg-icon">{msgIcon(msg.type)}</span>
        <span className="msg-id">[{msg.id}]</span>
        <span className="msg-text">{expanded ? summary : truncated}</span>
      </div>
      {expanded && (
        <pre className="msg-full">{msgFull(msg)}</pre>
      )}
    </div>
  );
}

// ── Main panel ───────────────────────────────────────────────────────

export function ContextPanel() {
  const state = useMissionState();
  const dispatch = useMissionDispatch();
  const bottomRef = useRef<HTMLDivElement>(null);

  // Fetch system prompt on mount
  useEffect(() => {
    if (state.systemPrompt) return;
    fetch(`${apiBase()}/context/system-prompt`)
      .then((r) => r.json())
      .then((data) => {
        dispatch({ type: "SET_SYSTEM_PROMPT", prompt: data.system_prompt });
      })
      .catch(() => {});
  }, []);

  // Fetch MCP tools on mount
  useEffect(() => {
    if (state.mcpTools.length > 0) return;
    fetch(`${apiBase()}/context/mcp-tools`)
      .then((r) => r.json())
      .then((data) => {
        dispatch({ type: "SET_MCP_TOOLS", tools: data.tools });
      })
      .catch(() => {});
  }, []);

  // Auto-scroll message history to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [state.contextMessages.length]);

  const msgCount = state.contextMessages.length;

  return (
    <div className="panel context-panel">
      <div className="panel-title">CONTEXT PANEL</div>
      <div className="context-subtitle">
        Live view of what the model sees &mdash; messages, tool calls, and raw
        JSON.
      </div>

      <div className="context-scroll">
        {/* 1. System Prompt */}
        <Accordion title="System Prompt">
          <pre className="system-prompt-content">
            {state.systemPrompt || "Loading..."}
          </pre>
        </Accordion>

        {/* 2. Message History */}
        <Accordion
          title="Message History"
          badge={
            msgCount > 0 ? `${msgCount} event(s) logged this session` : undefined
          }
          defaultOpen={true}
        >
          {msgCount === 0 && (
            <div className="panel-empty">
              Waiting for agent messages...
            </div>
          )}
          {state.contextMessages.map((msg) => (
            <MessageItem key={msg.id} msg={msg} />
          ))}
          <div ref={bottomRef} />
        </Accordion>

        {/* 3. MCP Tools */}
        <Accordion
          title="MCP Tools"
          badge={
            state.mcpTools.length > 0
              ? `${state.mcpTools.length} tool(s)`
              : undefined
          }
        >
          <pre className="mcp-tools-content">
            {state.mcpTools.length > 0
              ? JSON.stringify(state.mcpTools, null, 2)
              : "Loading..."}
          </pre>
        </Accordion>
      </div>
    </div>
  );
}
