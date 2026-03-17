"""
Mission logger with coloured terminal output and JSON / TXT persistence.

Records reasoning steps, tool calls, survivor reports, and battery events
with full dataclass structure for later analysis and debrief generation.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from colorama import Fore, Style


# ═══════════════════════════════════════════════════════════════════════
#  Dataclasses
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class ReasoningEntry:
    """A single reasoning step produced by the LLM."""

    step: int
    text: str
    timestamp: str = field(default_factory=lambda: _now_iso())


@dataclass
class ToolCallEntry:
    """A tool invocation + result record."""

    step: int
    tool_name: str
    params: dict
    result: dict | None = None
    timestamp: str = field(default_factory=lambda: _now_iso())


@dataclass
class SurvivorReport:
    """A confirmed survivor detection."""

    step: int
    x: int
    y: int
    drone_id: str
    confidence: float
    timestamp: str = field(default_factory=lambda: _now_iso())


@dataclass
class BatteryEvent:
    """A battery-related event (low-battery warning, recall, death)."""

    step: int
    drone_id: str
    battery_level: int
    action: str  # "recall" | "warning" | "depleted"
    timestamp: str = field(default_factory=lambda: _now_iso())


# ═══════════════════════════════════════════════════════════════════════
#  Mission Logger
# ═══════════════════════════════════════════════════════════════════════


class MissionLogger:
    """
    Records all mission events to memory and writes JSON + TXT on save.

    Every log method also prints a coloured line to the terminal so devs
    can follow mission progress in real time.
    """

    def __init__(self, log_dir: str = "logs") -> None:
        self._log_dir = Path(log_dir)
        self._reasoning: list[ReasoningEntry] = []
        self._tool_calls: list[ToolCallEntry] = []
        self._survivors: list[SurvivorReport] = []
        self._battery_events: list[BatteryEvent] = []
        self._start_time = _now_iso()

    # ── logging methods ─────────────────────────────────────────────

    def log_reasoning(self, step: int, text: str) -> None:
        """Log an LLM reasoning step (CYAN)."""
        entry = ReasoningEntry(step=step, text=text)
        self._reasoning.append(entry)
        print(f"{Fore.CYAN}[STEP {step:>3} · REASONING]{Style.RESET_ALL} {text[:200]}")

    def log_tool_call(
        self,
        step: int,
        tool_name: str,
        params: dict,
        result: dict | None = None,
    ) -> None:
        """Log a tool call with optional result (YELLOW)."""
        entry = ToolCallEntry(
            step=step, tool_name=tool_name, params=params, result=result
        )
        self._tool_calls.append(entry)
        print(
            f"{Fore.YELLOW}[STEP {step:>3} · TOOL]{Style.RESET_ALL} "
            f"{tool_name}({params}) → {result}"
        )

    def log_survivor(
        self,
        step: int,
        x: int,
        y: int,
        drone_id: str,
        confidence: float,
    ) -> None:
        """Log a survivor detection (GREEN + emoji)."""
        entry = SurvivorReport(
            step=step, x=x, y=y, drone_id=drone_id, confidence=confidence
        )
        self._survivors.append(entry)
        print(
            f"{Fore.GREEN}[STEP {step:>3} · SURVIVOR]{Style.RESET_ALL} "
            f"at ({x},{y}) by {drone_id} conf={confidence:.2f}"
        )

    def log_battery_event(
        self,
        step: int,
        drone_id: str,
        battery_level: int,
        action: str,
    ) -> None:
        """Log a battery event — recall / warning / depleted (RED)."""
        entry = BatteryEvent(
            step=step,
            drone_id=drone_id,
            battery_level=battery_level,
            action=action,
        )
        self._battery_events.append(entry)
        print(
            f"{Fore.RED}[STEP {step:>3} · 🔋 BATTERY]{Style.RESET_ALL} "
            f"{drone_id} at {battery_level}% → {action}"
        )

    # ── summary & persistence ──────────────────────────────────────

    def get_summary(self) -> dict:
        """Return a dict summarising the entire mission."""
        return {
            "start_time": self._start_time,
            "end_time": _now_iso(),
            "total_steps": self._get_max_step(),
            "reasoning_count": len(self._reasoning),
            "tool_calls_made": len(self._tool_calls),
            "survivors_found": len(self._survivors),
            "battery_events": len(self._battery_events),
            "survivor_details": [asdict(s) for s in self._survivors],
            "battery_details": [asdict(b) for b in self._battery_events],
        }

    def save(self, log_dir: str | Path | None = None) -> tuple[Path, Path]:
        """
        Write mission log as JSON and human-readable TXT.

        Returns:
            Tuple of (json_path, txt_path).
        """
        out_dir = Path(log_dir) if log_dir else self._log_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        json_path = out_dir / f"mission_{ts}.json"
        txt_path = out_dir / f"mission_{ts}.txt"

        # ── JSON ────────────────────────────────────────────────────
        payload = {
            "summary": self.get_summary(),
            "reasoning": [asdict(r) for r in self._reasoning],
            "tool_calls": [asdict(t) for t in self._tool_calls],
            "survivors": [asdict(s) for s in self._survivors],
            "battery_events": [asdict(b) for b in self._battery_events],
        }
        json_path.write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )

        # ── TXT ─────────────────────────────────────────────────────
        lines: list[str] = ["MISI BAYANG — Mission Log", "=" * 50, ""]
        for r in self._reasoning:
            lines.append(f"[Step {r.step}] REASONING: {r.text}")
        lines.append("")
        for t in self._tool_calls:
            lines.append(
                f"[Step {t.step}] TOOL: {t.tool_name}({t.params}) → {t.result}"
            )
        lines.append("")
        for s in self._survivors:
            lines.append(
                f"[Step {s.step}] SURVIVOR at ({s.x},{s.y}) "
                f"by {s.drone_id} conf={s.confidence}"
            )
        lines.append("")
        for b in self._battery_events:
            lines.append(
                f"[Step {b.step}] BATTERY: {b.drone_id} "
                f"at {b.battery_level}% → {b.action}"
            )
        lines.append("")
        lines.append("=" * 50)
        summary = self.get_summary()
        lines.append(f"Total steps: {summary['total_steps']}")
        lines.append(f"Survivors found: {summary['survivors_found']}")
        lines.append(f"Tool calls: {summary['tool_calls_made']}")
        lines.append(f"Battery events: {summary['battery_events']}")

        txt_path.write_text("\n".join(lines), encoding="utf-8")

        print(f"{Fore.GREEN}[LOGGER]{Style.RESET_ALL} Saved → {json_path} + {txt_path}")
        return json_path, txt_path

    # ── internal helpers ────────────────────────────────────────────

    def _get_max_step(self) -> int:
        """Highest step number seen across all entries."""
        steps = (
            [r.step for r in self._reasoning]
            + [t.step for t in self._tool_calls]
            + [s.step for s in self._survivors]
            + [b.step for b in self._battery_events]
        )
        return max(steps) if steps else 0


# ── module-level helpers ────────────────────────────────────────────


def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(tz=timezone.utc).isoformat()
