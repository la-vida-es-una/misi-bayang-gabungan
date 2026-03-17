"""
Centralized logging bootstrap for backend runtime.

Provides:
- configure_logging: unified log level/format for uvicorn + app modules
- enable_function_call_tracing: function-entry tracing for backend source files
"""

from __future__ import annotations

import atexit
import logging
import sys
import threading
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging format/level once for the whole backend."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )

    logging.getLogger("uvicorn").setLevel(numeric_level)
    logging.getLogger("uvicorn.error").setLevel(numeric_level)
    logging.getLogger("uvicorn.access").setLevel(numeric_level)


def _should_trace(frame) -> bool:
    filename = frame.f_code.co_filename
    if not isinstance(filename, str):
        return False
    if not filename:
        return False
    if filename.startswith("<"):
        return False
    raw_path = Path(filename)
    if not raw_path.is_absolute():
        return False

    try:
        path = raw_path.resolve()
    except OSError:
        return False

    if path == Path(__file__).resolve():
        return False

    path_str = str(path)
    if not path_str.startswith(str(_BACKEND_ROOT)):
        return False
    if "/tests/" in path_str or "/.venv/" in path_str:
        return False
    if path.name == "<frozen importlib._bootstrap>":
        return False
    return True


class _CallTracer:
    def __init__(self) -> None:
        self._logger = logging.getLogger("trace.calls")

    @staticmethod
    def _stack_depth(frame) -> int:
        depth = 0
        current = frame.f_back
        while current is not None and depth < 8:
            if _should_trace(current):
                depth += 1
            current = current.f_back
        return depth

    def __call__(self, frame, event, arg):
        try:
            if event != "call":
                return
            if not _should_trace(frame):
                return

            code = frame.f_code
            if code.co_name == "<module>":
                return

            module_name = frame.f_globals.get("__name__", "unknown")
            if module_name.startswith("importlib."):
                return
            indent = "  " * self._stack_depth(frame)
            self._logger.info("%s→ %s.%s", indent, module_name, code.co_name)
        except Exception:
            return


def _disable_profiles() -> None:
    sys.setprofile(None)
    threading.setprofile(None)


def enable_function_call_tracing(enabled: bool) -> None:
    """Enable/disable global function-entry tracing for backend code."""
    if not enabled:
        _disable_profiles()
        return

    tracer = _CallTracer()
    sys.setprofile(tracer)
    threading.setprofile(tracer)
    atexit.register(_disable_profiles)
