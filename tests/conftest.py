"""Общие фикстуры и хелперы тестов."""

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
from langchain.agents.middleware.types import ToolCallRequest
from langchain.tools import ToolRuntime
from langchain_core.tools import BaseTool

from hr_agent.context import RunContext


@pytest.fixture
def author_ctx() -> RunContext:
    """Обычный сотрудник без особых групп."""
    return RunContext(
        author_id="100001",
        groups=frozenset({"employees"}),
        role="сотрудник",
        today=date(2026, 8, 25),
    )


def make_runtime(context: RunContext, tool_call_id: str = "call_1") -> ToolRuntime[RunContext]:
    """ToolRuntime вне графа — так его собирает ToolNode при реальном вызове."""
    return ToolRuntime(
        state={},
        context=context,
        config={},
        stream_writer=lambda _: None,
        tool_call_id=tool_call_id,
        store=None,
        tools=[],
    )


async def call_tool(
    tool: BaseTool,
    args: dict[str, Any],
    context: RunContext | None = None,
    tool_call_id: str = "call_1",
) -> Any:
    """Вызвать тулзу с инжектированным runtime и получить её сырой результат.

    Аргументы передаются словарём, а не tool_call'ом: при вызове tool_call'ом langchain
    завернул бы результат в ToolMessage, а нам в тестах нужен сам payload.
    """
    payload = dict(args)
    if context is not None:
        payload["runtime"] = make_runtime(context, tool_call_id)
    return await tool.ainvoke(payload)


def make_context(author_id: str, groups: set[str], role: str = "сотрудник") -> RunContext:
    """Контекст произвольного автора обращения."""
    return RunContext(
        author_id=author_id,
        groups=frozenset(groups),
        role=role,
        today=date(2026, 8, 25),
    )


def make_tool_request(
    tool: BaseTool,
    args: dict[str, Any],
    context: RunContext,
    tool_call_id: str = "call_1",
) -> ToolCallRequest:
    """Запрос вызова тулзы в том виде, в каком его видит middleware."""
    return ToolCallRequest(
        tool_call={"name": tool.name, "id": tool_call_id, "type": "tool_call", "args": args},
        tool=tool,
        state={},
        runtime=SimpleNamespace(context=context),
    )
