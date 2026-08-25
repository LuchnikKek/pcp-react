"""Подстановка даты и роли в system prompt (ARCHITECTURE.md §2.6).

Табельный номер автора в промпт не попадает — только роль и сегодняшняя дата.
"""

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import SystemMessage

from hr_agent.context import RunContext
from hr_agent.prompts import SYSTEM_PROMPT


class DynamicPromptMiddleware(AgentMiddleware):
    """Собирает system prompt из шаблона и контекста запуска."""

    def __init__(self, template: str = SYSTEM_PROMPT) -> None:
        super().__init__()
        self.template = template

    def _rendered(self, request: ModelRequest) -> ModelRequest:
        context: RunContext = request.runtime.context
        prompt = self.template.format(today=context.today.isoformat(), role=context.role)
        return request.override(system_message=SystemMessage(prompt))

    def wrap_model_call(self, request: ModelRequest, handler: Any) -> Any:
        return handler(self._rendered(request))

    async def awrap_model_call(self, request: ModelRequest, handler: Any) -> Any:
        return await handler(self._rendered(request))
