"""Событие «прогресс» перед вызовом тулзы (ARCHITECTURE.md §2.6).

Шаблонные тексты, ноль вызовов модели. Пишутся в custom-stream — runtime отдаёт последний
такой текст фронту, когда не укладывается в бюджет ответа.
"""

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.config import get_stream_writer
from langgraph.types import Command

from hr_agent.prompts import DEFAULT_PROGRESS, PROGRESS_TEXTS


class ProgressMiddleware(AgentMiddleware):
    """Публикует текст прогресса на каждый вызов тулзы."""

    def __init__(self, texts: dict[str, str] | None = None) -> None:
        super().__init__()
        self.texts = PROGRESS_TEXTS if texts is None else texts

    def _emit(self, request: ToolCallRequest) -> None:
        text = self.texts.get(request.tool_call["name"], DEFAULT_PROGRESS)
        try:
            writer = get_stream_writer()
        except RuntimeError:  # вне запуска графа писать некуда
            return
        if writer is not None:
            writer({"progress": text})

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Any,
    ) -> ToolMessage | Command[Any]:
        self._emit(request)
        return handler(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Any,
    ) -> ToolMessage | Command[Any]:
        self._emit(request)
        return await handler(request)
