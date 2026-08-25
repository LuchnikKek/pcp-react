from hr_agent.tools.api import (
    API_TOOLS,
    compare_training,
    get_assignment,
    get_hr_partner,
    get_hr_service_contacts,
    get_training_history,
    get_vacation_balance,
)
from hr_agent.tools.types import extract_employee_refs
from tests.conftest import call_tool


async def test_training_history_resolves_me(author_ctx):
    result = await call_tool(get_training_history, {"employee_id": "me"}, context=author_ctx)
    assert result["employee_id"] == "100001"
    assert {c["id"] for c in result["courses"]} == {19, 21, 17}
    # результаты — сущности с id и именем, а не голые числа
    assert all(c["name"] for c in result["courses"])


async def test_training_history_unknown_employee_returns_text_error(author_ctx):
    result = await call_tool(get_training_history, {"employee_id": "999999"}, context=author_ctx)
    assert result.startswith("Ошибка:")


async def test_assignment_reason(author_ctx):
    result = await call_tool(
        get_assignment, {"employee_id": "me", "course_id": 17}, context=author_ctx
    )
    assert result["assigned"] is True
    assert "резерв" in result["reason"]
    assert result["assigned_by"] == {"id": "100010", "name": "Сидоров Пётр Андреевич"}
    assert result["due_at"] == "2026-09-30"


async def test_assignment_absent_and_bad_course(author_ctx):
    absent = await call_tool(
        get_assignment, {"employee_id": "me", "course_id": 20}, context=author_ctx
    )
    assert absent["assigned"] is False

    bad = await call_tool(
        get_assignment, {"employee_id": "me", "course_id": 999}, context=author_ctx
    )
    assert bad == "Ошибка: Курс с ID 999 не найден"


async def test_compare_training_list_subject(author_ctx):
    result = await call_tool(
        compare_training,
        {"employee_ids": ["100001", "100003"], "course_ids": [19, 22]},
        context=author_ctx,
    )
    by_employee = {r["employee_id"]: r for r in result["results"]}
    assert [c["completed"] for c in by_employee["100001"]["courses"]] == [True, False]
    assert [c["completed"] for c in by_employee["100003"]["courses"]] == [True, True]


async def test_compare_training_rejects_unknown_course(author_ctx):
    result = await call_tool(
        compare_training,
        {"employee_ids": ["me"], "course_ids": [19, 999]},
        context=author_ctx,
    )
    assert result.startswith("Ошибка:")


async def test_hr_partner_and_vacation(author_ctx):
    partner = await call_tool(get_hr_partner, {"employee_id": "me"}, context=author_ctx)
    assert partner["hr_partner"]["name"] == "Кузнецова Ольга Павловна"

    balance = await call_tool(get_vacation_balance, {"employee_id": "me"}, context=author_ctx)
    assert balance == {"employee_id": "100001", "days_left": 14}


async def test_service_contacts_has_no_subject():
    result = await call_tool(get_hr_service_contacts, {})
    assert "hotline" in result
    assert extract_employee_refs(get_hr_service_contacts, {}) == []


def test_every_api_tool_has_description_in_kb_lexicon():
    """Описание тулзы — механизм связки с инструкцией, пустых быть не должно."""
    for tool in API_TOOLS:
        assert tool.description
        assert len(tool.description) > 40
