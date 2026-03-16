/**
 * SimulationCanvas — renders the SAR simulation via HTML Canvas.
 *
 * All drawing logic from the original canvas.ts, wrapped in a React component
 * that reads live state from the mission store.
 */

import { useEffect, useRef } from "react";
import { useMissionState } from "./store";
import type { TickEvent } from "./types";

// ── Constants ──────────────────────────────────────────────────────────
const DRONE_COLORS = ["#4af", "#f4a", "#4fa", "#fa4", "#a4f", "#ff8", "#8ff"];
const DRONE_NAMES = [
  "ALPHA",
  "BRAVO",
  "CHARLIE",
  "DELTA",
  "ECHO",
  "FOXTROT",
  "GOLF",
];

// ── Helpers ────────────────────────────────────────────────────────────
function hexAlpha(hex: string, a: number): string {
  const r = parseInt(hex.slice(1, 3), 16) || 170;
  const g = parseInt(hex.slice(3, 5), 16) || 170;
  const b = parseInt(hex.slice(5, 7), 16) || 255;
  return `rgba(${r},${g},${b},${a})`;
}

function gridToNorm(
  gx: number,
  gy: number,
  gw: number,
  gh: number,
): { nx: number; ny: number } {
  return { nx: gx / (gw - 1), ny: 1 - gy / (gh - 1) };
}

// ── Drawing functions ──────────────────────────────────────────────────

function worldToScreen(
  nx: number,
  ny: number,
  cw: number,
  ch: number,
  cam: { x: number; y: number; scale: number },
) {
  return {
    x: cw / 2 + cam.x + (nx - 0.5) * cw * cam.scale,
    y: ch / 2 + cam.y + (ny - 0.5) * ch * cam.scale,
  };
}

function drawTerrain(
  ctx: CanvasRenderingContext2D,
  cw: number,
  ch: number,
  cam: { x: number; y: number },
) {
  ctx.fillStyle = "#060d14";
  ctx.fillRect(0, 0, cw, ch);
  ctx.strokeStyle = "rgba(40,100,160,0.07)";
  ctx.lineWidth = 0.5;
  const gs = 40;
  const ox = (cam.x * 0.3) % gs;
  const oy = (cam.y * 0.3) % gs;
  for (let x = -gs + ox; x < cw + gs; x += gs) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, ch);
    ctx.stroke();
  }
  for (let y = -gs + oy; y < ch + gs; y += gs) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(cw, y);
    ctx.stroke();
  }
}

function drawObstacles(
  ctx: CanvasRenderingContext2D,
  state: TickEvent,
  cw: number,
  ch: number,
  cam: { x: number; y: number; scale: number },
) {
  if (!state.obstacles?.length) return;
  const gw = state.grid.width,
    gh = state.grid.height;
  const cellW = (cw * cam.scale) / (gw - 1);
  const cellH = (ch * cam.scale) / (gh - 1);
  ctx.fillStyle = "rgba(28,52,76,0.78)";
  ctx.strokeStyle = "rgba(40,100,160,0.22)";
  ctx.lineWidth = 0.5;
  for (const obs of state.obstacles) {
    for (const cell of obs.cells) {
      const { nx, ny } = gridToNorm(cell[0], cell[1], gw, gh);
      const p = worldToScreen(nx, ny, cw, ch, cam);
      ctx.fillRect(p.x - cellW / 2, p.y - cellH / 2, cellW, cellH);
      ctx.strokeRect(p.x - cellW / 2, p.y - cellH / 2, cellW, cellH);
    }
  }
}

function drawCommMesh(
  ctx: CanvasRenderingContext2D,
  state: TickEvent,
  cw: number,
  ch: number,
  cam: { x: number; y: number; scale: number },
) {
  const gw = state.grid.width,
    gh = state.grid.height;
  const norms = state.drones.map((d) => gridToNorm(d.x, d.y, gw, gh));
  const THRESH = 0.2;
  for (let i = 0; i < norms.length; i++) {
    for (let j = i + 1; j < norms.length; j++) {
      const dx = norms[i].nx - norms[j].nx;
      const dy = norms[i].ny - norms[j].ny;
      if (Math.sqrt(dx * dx + dy * dy) < THRESH) {
        const p1 = worldToScreen(norms[i].nx, norms[i].ny, cw, ch, cam);
        const p2 = worldToScreen(norms[j].nx, norms[j].ny, cw, ch, cam);
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.strokeStyle = "rgba(68,170,255,0.07)";
        ctx.lineWidth = 0.5;
        ctx.setLineDash([3, 5]);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }
  }
}

function drawTrails(
  ctx: CanvasRenderingContext2D,
  state: TickEvent,
  trails: Record<number, { nx: number; ny: number }[]>,
  cw: number,
  ch: number,
  cam: { x: number; y: number; scale: number },
) {
  state.drones.forEach((drone, i) => {
    const trail = trails[drone.id];
    if (!trail || trail.length < 2) return;
    const color = DRONE_COLORS[i % DRONE_COLORS.length];
    for (let j = 1; j < trail.length; j++) {
      const alpha = (j / trail.length) * 0.5;
      const p1 = worldToScreen(trail[j - 1].nx, trail[j - 1].ny, cw, ch, cam);
      const p2 = worldToScreen(trail[j].nx, trail[j].ny, cw, ch, cam);
      ctx.beginPath();
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
      ctx.strokeStyle = hexAlpha(color, alpha);
      ctx.lineWidth = 1.2;
      ctx.stroke();
    }
  });
}

function drawBase(
  ctx: CanvasRenderingContext2D,
  state: TickEvent,
  cw: number,
  ch: number,
  cam: { x: number; y: number; scale: number },
) {
  const gw = state.grid.width,
    gh = state.grid.height;
  const { nx, ny } = gridToNorm(state.base_pos[0], state.base_pos[1], gw, gh);
  const p = worldToScreen(nx, ny, cw, ch, cam);
  const sc = cam.scale;

  ctx.beginPath();
  ctx.arc(p.x, p.y, 14 * sc, 0, Math.PI * 2);
  ctx.strokeStyle = "rgba(68,170,255,0.5)";
  ctx.lineWidth = 1;
  ctx.setLineDash([3, 3]);
  ctx.stroke();
  ctx.setLineDash([]);

  ctx.beginPath();
  ctx.arc(p.x, p.y, 6 * sc, 0, Math.PI * 2);
  ctx.fillStyle = "#4af";
  ctx.globalAlpha = 0.85;
  ctx.fill();
  ctx.globalAlpha = 1;

  ctx.fillStyle = "#0af";
  ctx.font = `${Math.round(7 * sc)}px 'Courier New'`;
  ctx.fillText("BASE", p.x - 11 * sc, p.y + 20 * sc);
}

function drawSurvivors(
  ctx: CanvasRenderingContext2D,
  state: TickEvent,
  cw: number,
  ch: number,
  cam: { x: number; y: number; scale: number },
) {
  const gw = state.grid.width,
    gh = state.grid.height;
  const sc = cam.scale;
  for (const sv of state.survivors) {
    if (sv.state === "unseen") continue;
    const { nx, ny } = gridToNorm(sv.x, sv.y, gw, gh);
    const p = worldToScreen(nx, ny, cw, ch, cam);
    if (sv.state === "found") {
      const pulse = Math.sin(Date.now() * 0.006) * 3;
      ctx.beginPath();
      ctx.arc(p.x, p.y, (10 + pulse) * sc, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(255,80,80,0.35)";
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(p.x, p.y, 4 * sc, 0, Math.PI * 2);
      ctx.fillStyle = "#f44";
      ctx.fill();
    } else if (sv.state === "rescued") {
      ctx.beginPath();
      ctx.arc(p.x, p.y, 8 * sc, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(80,255,130,0.35)";
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(p.x, p.y, 4 * sc, 0, Math.PI * 2);
      ctx.fillStyle = "#4f8";
      ctx.fill();
    }
  }
}

function drawDrones(
  ctx: CanvasRenderingContext2D,
  state: TickEvent,
  trails: Record<number, { nx: number; ny: number }[]>,
  cw: number,
  ch: number,
  cam: { x: number; y: number; scale: number },
) {
  const gw = state.grid.width,
    gh = state.grid.height;
  const sc = cam.scale;
  state.drones.forEach((drone, i) => {
    const color = DRONE_COLORS[i % DRONE_COLORS.length];
    const name = DRONE_NAMES[i % DRONE_NAMES.length];
    const { nx, ny } = gridToNorm(drone.x, drone.y, gw, gh);
    const p = worldToScreen(nx, ny, cw, ch, cam);

    // Heading from trail
    let ang = 0;
    const trail = trails[drone.id];
    if (trail && trail.length >= 2) {
      const prev = trail[trail.length - 2];
      const curr = trail[trail.length - 1];
      ang = Math.atan2(curr.ny - prev.ny, curr.nx - prev.nx);
    }

    // Triangle
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate(ang);
    ctx.beginPath();
    ctx.moveTo(9 * sc, 0);
    ctx.lineTo(-5 * sc, -4 * sc);
    ctx.lineTo(-3 * sc, 0);
    ctx.lineTo(-5 * sc, 4 * sc);
    ctx.closePath();
    ctx.fillStyle = color;
    ctx.globalAlpha = 0.92;
    ctx.fill();
    ctx.restore();

    // Outer ring
    ctx.beginPath();
    ctx.arc(p.x, p.y, 12 * sc, 0, Math.PI * 2);
    ctx.strokeStyle = hexAlpha(color, 0.2);
    ctx.lineWidth = 1;
    ctx.stroke();

    // Battery arc
    const batt = Math.max(0, drone.battery) / 100;
    ctx.beginPath();
    ctx.arc(
      p.x,
      p.y,
      12 * sc,
      -Math.PI / 2,
      -Math.PI / 2 + Math.PI * 2 * batt,
    );
    ctx.strokeStyle = hexAlpha(color, batt > 0.2 ? 0.7 : 1.0);
    ctx.lineWidth = 2;
    ctx.stroke();

    // Label
    ctx.fillStyle = color;
    ctx.font = `${Math.round(8 * sc)}px 'Courier New'`;
    ctx.globalAlpha = 0.75;
    ctx.fillText(name, p.x + 14 * sc, p.y - 6 * sc);
    ctx.globalAlpha = 1;
  });
}

// ── React Component ────────────────────────────────────────────────────

export function SimulationCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const { liveState, droneTrails } = useMissionState();

  // Store latest state in refs so the rAF loop doesn't need re-registration
  const stateRef = useRef(liveState);
  const trailsRef = useRef(droneTrails);
  stateRef.current = liveState;
  trailsRef.current = droneTrails;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;
    const cam = { x: 0, y: 0, scale: 1 };
    let raf: number;

    function resize() {
      const r = canvas!.getBoundingClientRect();
      canvas!.width = r.width;
      canvas!.height = r.height;
    }
    resize();
    window.addEventListener("resize", resize);

    function frame() {
      raf = requestAnimationFrame(frame);
      const cw = canvas!.width;
      const ch = canvas!.height;
      cam.x += (0 - cam.x) * 0.05;
      cam.y += (0 - cam.y) * 0.05;
      cam.scale += (1 - cam.scale) * 0.04;

      drawTerrain(ctx, cw, ch, cam);
      const state = stateRef.current;
      const trails = trailsRef.current;
      if (state) {
        drawCommMesh(ctx, state, cw, ch, cam);
        drawObstacles(ctx, state, cw, ch, cam);
        drawTrails(ctx, state, trails, cw, ch, cam);
        drawBase(ctx, state, cw, ch, cam);
        drawSurvivors(ctx, state, cw, ch, cam);
        drawDrones(ctx, state, trails, cw, ch, cam);
      }
    }
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return <canvas ref={canvasRef} id="c3d" />;
}
