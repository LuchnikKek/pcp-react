"""Тулзы домена «кадровые данные сотрудника» (ARCHITECTURE.md §2.3)."""

from typing import Any

from langchain.tools import ToolRuntime, tool

from hr_agent.context import RunContext
from hr_agent.synthetic import api
from hr_agent.tools.types import EmployeeRef, resolve, tool_error


@tool
async def get_hr_partner(
    employee_id: EmployeeRef,
    runtime: ToolRuntime[RunContext],
) -> dict[str, Any] | str:
    """HR-партнёр, закреплённый за сотрудником: имя и должность.

    employee_id — табельный номер сотрудника или "me", если вопрос про автора обращения.
    """
    eid = resolve(employee_id, runtime.context.author_id)
    try:
        partner = await api.hr_partner(eid)
    except api.ApiNotFound:
        return tool_error(f"Сотрудник {eid} не найден")

    if partner is None:
        return {"employee_id": eid, "hr_partner": None}
    return {
        "employee_id": eid,
        "hr_partner": {"id": partner.id, "name": partner.name, "position": partner.position},
    }


@tool
async def get_vacation_balance(
    employee_id: EmployeeRef,
    runtime: ToolRuntime[RunContext],
) -> dict[str, Any] | str:
    """Остаток дней ежегодного оплачиваемого отпуска у сотрудника.

    employee_id — табельный номер сотрудника или "me", если вопрос про автора обращения.
    """
    eid = resolve(employee_id, runtime.context.author_id)
    try:
        days = await api.vacation_balance(eid)
    except api.ApiNotFound:
        return tool_error(f"Сотрудник {eid} не найден")
    return {"employee_id": eid, "days_left": days}


@tool
async def get_hr_service_contacts() -> dict[str, Any]:
    """Контакты и режим работы кадровой службы: телефон, почта, кабинет, часы приёма.

    Общая справка, не привязанная к конкретному сотруднику.
    """
    return await api.hr_service_contacts()
