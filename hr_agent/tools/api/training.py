"""Тулзы домена «обучение и курсы» (ARCHITECTURE.md §2.3, §2.5)."""

from typing import Any

from langchain.tools import ToolRuntime, tool

from hr_agent.context import RunContext
from hr_agent.synthetic import api
from hr_agent.synthetic.courses import COURSES
from hr_agent.tools.types import EmployeeRef, resolve, tool_error, truncated


def _course_name(course_id: int) -> str:
    course = COURSES.get(course_id)
    return course.name if course else f"курс {course_id}"


@tool
async def get_training_history(
    employee_id: EmployeeRef,
    runtime: ToolRuntime[RunContext],
) -> dict[str, Any] | str:
    """История обучения сотрудника: пройденные и текущие курсы со статусом и датой завершения.

    employee_id — табельный номер сотрудника или "me", если вопрос про автора обращения.
    """
    eid = resolve(employee_id, runtime.context.author_id)
    try:
        records = await api.training_history(eid)
    except api.ApiNotFound:
        return tool_error(f"Сотрудник {eid} не найден")

    payload = {
        "employee_id": eid,
        "courses": [
            {
                "id": r.course_id,
                "name": _course_name(r.course_id),
                "status": r.status,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            }
            for r in records
        ],
    }
    return truncated(payload, key="courses")


@tool
async def get_assignment(
    employee_id: EmployeeRef,
    course_id: int,
    runtime: ToolRuntime[RunContext],
) -> dict[str, Any] | str:
    """Причина назначения курса сотруднику, срок прохождения и кто назначил.

    employee_id — табельный номер сотрудника или "me". course_id — идентификатор курса,
    полученный из поиска курса по названию.
    """
    eid = resolve(employee_id, runtime.context.author_id)
    try:
        found = await api.assignment(eid, course_id)
    except api.ApiNotFound as exc:
        missing = exc.args[0]
        if missing == eid:
            return tool_error(f"Сотрудник {eid} не найден")
        return tool_error(f"Курс с ID {course_id} не найден")

    if found is None:
        return {
            "employee_id": eid,
            "course": {"id": course_id, "name": _course_name(course_id)},
            "assigned": False,
        }

    assigner = await api.get_employee(found.assigned_by_id)
    return {
        "employee_id": eid,
        "course": {"id": found.course_id, "name": _course_name(found.course_id)},
        "assigned": True,
        "reason": found.reason,
        "assigned_by": {"id": assigner.id, "name": assigner.name},
        "assigned_at": found.assigned_at.isoformat(),
        "due_at": found.due_at.isoformat(),
    }


@tool
async def compare_training(
    employee_ids: list[EmployeeRef],
    course_ids: list[int],
    runtime: ToolRuntime[RunContext],
) -> dict[str, Any] | str:
    """Проверить, прошли ли указанные сотрудники указанные курсы.

    employee_ids — табельные номера сотрудников или "me". course_ids — идентификаторы курсов,
    полученные из поиска курса по названию.
    """
    author_id = runtime.context.author_id
    unknown = [cid for cid in course_ids if cid not in COURSES]
    if unknown:
        return tool_error(f"Курсы не найдены: {', '.join(str(c) for c in unknown)}")

    results: list[dict[str, Any]] = []
    for ref in employee_ids:
        eid = resolve(ref, author_id)
        try:
            records = await api.training_history(eid)
        except api.ApiNotFound:
            return tool_error(f"Сотрудник {eid} не найден")
        completed = {r.course_id for r in records if r.status == "completed"}
        results.append(
            {
                "employee_id": eid,
                "courses": [
                    {"id": cid, "name": _course_name(cid), "completed": cid in completed}
                    for cid in course_ids
                ],
            }
        )
    return truncated({"results": results}, key="results")
