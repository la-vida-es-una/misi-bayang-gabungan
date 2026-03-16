"""
LangGraph callback handler that bridges LLM events to AgentObserverProtocol.

Captures reasoning text from LLM responses and tool call start/end events,
forwarding them to the WebSocketObserver for real-time frontend display.
"""

from __future__ import annotations

import json
import logging
from typing import Any, TYPE_CHECKING

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

if TYPE_CHECKING:
    from .interfaces import AgentObserverProtocol

logger = logging.getLogger(__name__)


class ObserverCallbackHandler(BaseCallbackHandler):
    """
    LangChain callback handler that forwards LLM reasoning and tool calls
    to an AgentObserverProtocol implementation.
    """

    def __init__(self, observer: "AgentObserverProtocol") -> None:
        super().__init__()
        self._observer = observer
        self._step = 0
        self._pending_tool: dict[str, Any] | None = None

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Extract reasoning text from LLM response and forward to observer."""
        for gen_list in response.generations:
            for gen in gen_list:
                text = gen.text.strip() if gen.text else ""
                if text:
                    self._step += 1
                    self._observer.on_reasoning(self._step, text)

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        """Capture tool invocation start for pairing with on_tool_end."""
        tool_name = serialized.get("name", "unknown")
        try:
            params = json.loads(input_str) if input_str else {}
        except (json.JSONDecodeError, TypeError):
            params = {"raw_input": input_str}
        self._pending_tool = {"name": tool_name, "params": params}

    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        """Pair with stored tool start info and forward to observer."""
        if self._pending_tool is None:
            return
        try:
            result = json.loads(output) if output else {}
        except (json.JSONDecodeError, TypeError):
            result = {"raw_output": output}
        self._observer.on_tool_call(
            self._pending_tool["name"],
            self._pending_tool["params"],
            result,
        )
        self._pending_tool = None

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        """Forward tool errors as tool calls with error info."""
        if self._pending_tool is None:
            return
        self._observer.on_tool_call(
            self._pending_tool["name"],
            self._pending_tool["params"],
            {"error": str(error)},
        )
        self._pending_tool = None
