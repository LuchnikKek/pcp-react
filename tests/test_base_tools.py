import pytest
from langgraph.types import Command
from pydantic import ValidationError

from hr_agent.tools.base import (
    TICKET_CONSTANTS,
    create_ticket,
    find_course,
    get_instruction,
    search,
)
from tests.conftest import call_tool


async def test_search_returns_top_text_when_gap_is_wide():
    result = await call_tool(search, {"query": "почему мне назначен курс"})
    assert result["candidates"][0]["id"] == "KB-001"
    assert result["candidates"][0]["type"] == "api"
    assert result["top_text"] is not None
    assert "Уточни у обратившегося" in result["top_text"]


async def test_search_withholds_top_text_when_candidates_are_close():
    """Кандидаты без отрыва: модель должна дочитать нужную инструкцию сама."""
    result = await call_tool(search, {"query": "курс обучение"})
    assert len(result["candidates"]) > 1
    assert result["top_text"] is None


async def test_search_without_matches():
    result = await call_tool(search, {"query": "прогноз погоды"})
    assert result["candidates"] == []
    assert result["top_text"] is None
    assert "hint" in result


async def test_get_instruction_found_and_missing():
    found = await call_tool(get_instruction, {"instruction_id": "KB-006"})
    assert found["type"] == "rag"
    assert "по графику отпусков" in found["text"]

    missing = await call_tool(get_instruction, {"instruction_id": "KB-999"})
    assert missing.startswith("Ошибка:")


async def test_find_course_returns_entities_with_id_and_name():
    result = await call_tool(find_course, {"name_part": "скрам"})
    assert result["courses"] == [{"id": 17, "name": "Школа скрам-мастеров"}]

    empty = await call_tool(find_course, {"name_part": "квантовая физика"})
    assert empty["courses"] == []


async def test_create_ticket_fills_state_and_resolves_me(author_ctx):
    result = await call_tool(
        create_ticket,
        {
            "category": "Справки",
            "employee_id": "me",
            "description": "Нужна справка о доходах",
            "reason": "о доходах, электронно, 1 экземпляр",
        },
        context=author_ctx,
    )
    assert isinstance(result, Command)
    ticket = result.update["ticket"]
    assert ticket["employee_id"] == "100001"  # "me" развёрнут, номера в тексте не было
    assert ticket["category"] == "Справки"
    assert TICKET_CONSTANTS.items() <= ticket.items()
    assert result.update["messages"][0].tool_call_id == "call_1"


async def test_create_ticket_missing_required_field_is_validation_error(author_ctx):
    """Нет обязательного поля → ошибка валидации, которую агент вернёт модели текстом."""
    with pytest.raises(ValidationError) as excinfo:
        await call_tool(
            create_ticket,
            {
                "category": "Справки",
                "employee_id": "me",
                "description": "Нужна справка о доходах",
            },
            context=author_ctx,
        )
    assert {e["loc"][0] for e in excinfo.value.errors()} == {"reason"}


async def test_create_ticket_rejects_garbage_employee_ref(author_ctx):
    with pytest.raises(ValidationError):
        await call_tool(
            create_ticket,
            {
                "category": "Справки",
                "employee_id": "сотрудник Иванов",
                "description": "Нужна справка",
                "reason": "о доходах",
            },
            context=author_ctx,
        )
