"""Кастомный state агента (ARCHITECTURE.md §2.2).

`create_agent` расширяет state только через middleware, поэтому схема объявляется
носителем-мидлварью без хуков.
"""

from typing import Any, NotRequired

from langchain.agents.middleware import AgentMiddleware, AgentState


class HRState(AgentState):
    """State агента: сообщения (из AgentState) + подготовленная заявка."""

    ticket: NotRequired[dict[str, Any] | None]


class HRStateMiddleware(AgentMiddleware[HRState]):
    """Носитель схемы state. Хуков не реализует."""

    state_schema = HRState
