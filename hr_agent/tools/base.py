"""Базовые тулзы, привязанные всегда (ARCHITECTURE.md §2.4).

Описания тулзов намеренно написаны в лексике инструкций БЗ — это основной механизм связки
«инструкция → тулза» после отказа от технической разметки базы знаний.
"""

from typing import Annotated, Any

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from pydantic import Field

from hr_agent.config import settings
from hr_agent.context import RunContext
from hr_agent.synthetic import api
from hr_agent.tools.types import EmployeeRef, resolve, tool_error, truncated

_SEARCH_LIMIT = 5

TICKET_CONSTANTS: dict[str, str] = {"source": "hr-agent", "channel": "chat"}


@tool
async def search(query: str) -> dict[str, Any]:
    """Найти инструкцию по кадровому вопросу сотрудника в базе знаний.

    Вызывается первой на каждый новый вопрос: отпуск, обучение и курсы, справки,
    персональные данные, материальная помощь, увольнение, контакты кадровой службы.
    Возвращает список подходящих инструкций, а если одна из них подходит явно лучше
    остальных — сразу её полный текст в поле top_text.
    """
    ranked = await api.search_kb(query, limit=_SEARCH_LIMIT)
    if not ranked:
        return {
            "candidates": [],
            "top_text": None,
            "hint": "Ничего не найдено. Переформулируй запрос словами сотрудника.",
        }

    candidates = [{"id": i.id, "title": i.title, "type": i.type} for i, _ in ranked]

    top_score = ranked[0][1]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    gap = (top_score - second_score) / top_score if top_score else 0.0
    top_text = ranked[0][0].text if gap >= settings.gap_threshold else None

    return {"candidates": candidates, "top_text": top_text}


@tool
async def get_instruction(instruction_id: str) -> dict[str, Any] | str:
    """Прочитать полный текст инструкции из базы знаний по её идентификатору.

    Вызывается, когда search вернул несколько близких кандидатов или когда нужна
    другая инструкция из списка.
    """
    try:
        instruction = await api.get_instruction(instruction_id)
    except api.ApiNotFound:
        return tool_error(f"Инструкция {instruction_id} не найдена")
    return {
        "id": instruction.id,
        "title": instruction.title,
        "type": instruction.type,
        "text": instruction.text,
    }


@tool
async def find_course(name_part: str) -> dict[str, Any]:
    """Найти курс обучения по части названия.

    Возвращает список курсов с идентификаторами. Если курсов нашлось несколько,
    перечисли их сотруднику и попроси выбрать нужный.
    """
    courses = await api.find_course(name_part)
    payload = {
        "query": name_part,
        "courses": [{"id": c.id, "name": c.name} for c in courses],
    }
    return truncated(payload, key="courses")


@tool
async def create_ticket(
    runtime: ToolRuntime[RunContext],
    category: Annotated[str, Field(description="Категория заявки, названная в инструкции")],
    employee_id: Annotated[
        EmployeeRef,
        Field(description='Табельный номер сотрудника, которого касается заявка, или "me"'),
    ],
    description: Annotated[str, Field(description="Суть обращения словами сотрудника")],
    reason: Annotated[
        str,
        Field(
            description=(
                "Уточнение, которое требует инструкция: вид справки и способ получения, "
                "какие именно персональные данные меняются, основание материальной помощи"
            )
        ),
    ],
) -> Command:
    """Подготовить заявку в кадровую службу.

    Вызывать только после того, как инструкция предписывает создать заявку и все
    обязательные поля известны из диалога. Недостающие поля сначала спроси у сотрудника.
    """
    payload = {
        "category": category,
        "employee_id": resolve(employee_id, runtime.context.author_id),
        "description": description,
        "reason": reason,
        **TICKET_CONSTANTS,
    }
    return Command(
        update={
            "ticket": payload,
            "messages": [
                ToolMessage(
                    "Заявка подготовлена. Сообщи сотруднику её содержание.",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        }
    )


BASE_TOOLS = [search, get_instruction, find_course, create_ticket]
