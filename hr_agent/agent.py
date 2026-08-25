"""Сборка агента (ARCHITECTURE.md §2.6).

Порядок middleware важен: первый в списке — внешний. Проверено на установленной версии
langchain: «first defined = outermost».
"""

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ClearToolUsesEdit,
    ContextEditingMiddleware,
    ModelCallLimitMiddleware,
    SummarizationMiddleware,
    ToolRetryMiddleware,
)
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph

from hr_agent.config import settings
from hr_agent.context import RunContext
from hr_agent.middleware import AuthzMiddleware, DynamicPromptMiddleware, ProgressMiddleware
from hr_agent.models import build_model
from hr_agent.prompts import SUMMARY_PROMPT
from hr_agent.state import HRStateMiddleware
from hr_agent.tools.api import API_TOOLS
from hr_agent.tools.base import BASE_TOOLS

# Тексты инструкций и результаты поиска из контекста не вычищаем: на них держится
# следование инструкции в многоходовом диалоге.
_KEEP_IN_CONTEXT = ["search", "get_instruction"]


def build_agent(
    model: BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """Собрать граф агента.

    System prompt не передаётся статически: его на каждый вызов модели собирает
    `DynamicPromptMiddleware`, подставляя сегодняшнюю дату и роль пользователя.
    """
    model = model or build_model()
    return create_agent(
        model=model,
        tools=[*BASE_TOOLS, *API_TOOLS],
        context_schema=RunContext,
        middleware=[
            HRStateMiddleware(),
            DynamicPromptMiddleware(),
            AuthzMiddleware(),
            ProgressMiddleware(),
            ToolRetryMiddleware(max_retries=2),
            ContextEditingMiddleware(
                edits=[
                    ClearToolUsesEdit(
                        trigger=settings.ctx_edit_trigger,
                        keep=settings.ctx_edit_keep,
                        exclude_tools=_KEEP_IN_CONTEXT,
                        # аргументы прошлых вызовов остаются в контексте: именно они
                        # позволяют модели понять «а про другой курс?» как повтор шага
                        clear_tool_inputs=False,
                    )
                ]
            ),
            SummarizationMiddleware(
                model=model,
                trigger=("tokens", settings.summary_trigger),
                keep=("messages", settings.summary_keep_messages),
                summary_prompt=SUMMARY_PROMPT,
            ),
            ModelCallLimitMiddleware(run_limit=settings.model_call_limit, exit_behavior="end"),
        ],
        checkpointer=checkpointer or InMemorySaver(),
    )
