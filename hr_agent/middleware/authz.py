"""Авторизация вызовов тулзов (ARCHITECTURE.md §2.6).

Единственное место, где проверяются права: ни модель, ни сами тулзы этим не занимаются.
Субъекты извлекаются из схемы вызова по типу параметра `EmployeeRef`, а не по имени.
"""

import logging
import time
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from hr_agent.config import settings
from hr_agent.context import RunContext
from hr_agent.policy import DEFAULT_RULE, POLICY, Rule
from hr_agent.synthetic import api
from hr_agent.tools.types import SELF_REF, extract_employee_refs

logger = logging.getLogger(__name__)

_DENIED_TEMPLATE = (
    "Нет прав запрашивать эти данные по сотруднику {subject}. "
    "Сообщи пользователю, что доступ к данным этого сотрудника ограничен."
)


class ManagerCache:
    """TTL-кеш ответов `manager_of`: одна пара (автор, субъект) — один вызов API."""

    def __init__(self, ttl: float) -> None:
        self._ttl = ttl
        self._entries: dict[tuple[str, str], tuple[float, bool]] = {}

    async def is_manager(self, author_id: str, subject_id: str) -> bool:
        key = (author_id, subject_id)
        now = time.monotonic()
        cached = self._entries.get(key)
        if cached is not None and now - cached[0] < self._ttl:
            return cached[1]
        try:
            manager_id = await api.manager_of(subject_id)
        except api.ApiNotFound:
            manager_id = None
        result = manager_id == author_id
        self._entries[key] = (now, result)
        return result


class AuthzMiddleware(AgentMiddleware):
    """Проверяет права на субъектов вызова до исполнения тулзы."""

    def __init__(
        self,
        policy: dict[str, Rule] | None = None,
        manager_cache: ManagerCache | None = None,
    ) -> None:
        super().__init__()
        self.policy = POLICY if policy is None else policy
        self.cache = manager_cache or ManagerCache(settings.manager_cache_ttl)

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Any,
    ) -> ToolMessage | Command[Any]:
        """Синхронный путь не поддерживается: проверка прав ходит в API асинхронно.

        Падаем громко, чтобы синхронный запуск агента не прошёл мимо авторизации.
        """
        raise RuntimeError(
            "AuthzMiddleware работает только на асинхронном запуске агента "
            "(agent.ainvoke / agent.astream)"
        )

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Any,
    ) -> ToolMessage | Command[Any]:
        tool_name = request.tool_call["name"]
        context: RunContext = request.runtime.context
        subjects = extract_employee_refs(request.tool, request.tool_call["args"])
        rule = self.policy.get(tool_name, DEFAULT_RULE)

        for subject in subjects:
            if subject in (SELF_REF, context.author_id):
                continue
            if rule.groups & context.groups:
                continue
            if rule.manager_ok and await self.cache.is_manager(context.author_id, subject):
                continue

            logger.warning(
                "authz denied: author=%s tool=%s subject=%s",
                context.author_id,
                tool_name,
                subject,
            )
            return ToolMessage(
                content=_DENIED_TEMPLATE.format(subject=subject),
                tool_call_id=request.tool_call["id"],
                name=tool_name,
                status="error",
            )

        return await handler(request)
