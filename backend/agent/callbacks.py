"""
LangGraph callback handler that bridges LLM events to AgentObserverProtocol.

Captures reasoning text from LLM responses and tool call start/end events,
forwarding them to the WebSocketObserver for real-time frontend display.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

if TYPE_CHECKING:
    from .interfaces import AgentObserverProtocol


class ObserverCallbackHandler(BaseCallbackHandler):
    """
    LangChain callback handler that forwards LLM reasoning text
    to an AgentObserverProtocol implementation.

    Tool calls are reported directly from the tool wrappers in
    MissionOrchestrator._build_tools(), not through callbacks.
    """

    def __init__(self, observer: "AgentObserverProtocol") -> None:
        super().__init__()
        self._observer = observer
        self._step = 0

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Extract reasoning text from LLM response and forward to observer."""
        for gen_list in response.generations:
            for gen in gen_list:
                text = gen.text.strip() if gen.text else ""
                if text:
                    self._step += 1
                    self._observer.on_reasoning(self._step, text)
