"""Async-фасад над синтетическими данными — стоит на месте ~20 внутренних API.

Единственный модуль, который меняется при переезде на реальные системы: тулзы ходят только
сюда. Каждый вызов «сходит по сети» — задержка из `settings.synthetic_latency`, чтобы бюджет
SLA в runtime проверялся на непустых задержках.
"""

import asyncio

from hr_agent.config import settings
from hr_agent.synthetic.courses import (
    ASSIGNMENTS,
    COURSES,
    TRAINING_HISTORY,
    Assignment,
    Course,
    TrainingRecord,
)
from hr_agent.synthetic.directory import EMPLOYEES, HR_SERVICE_CONTACTS, Employee
from hr_agent.synthetic.kb import INSTRUCTIONS, Instruction, rank


class ApiNotFound(Exception):
    """Запрошенной сущности нет в системе-источнике."""


async def _latency() -> None:
    await asyncio.sleep(settings.synthetic_latency)


# --- авторизация ---------------------------------------------------------------------


async def get_groups(employee_id: str) -> frozenset[str]:
    """Группы доступа сотрудника (авторизационный эндпоинт)."""
    await _latency()
    employee = EMPLOYEES.get(employee_id)
    if employee is None:
        raise ApiNotFound(employee_id)
    return employee.groups


async def manager_of(employee_id: str) -> str | None:
    """Табельный номер руководителя сотрудника."""
    await _latency()
    employee = EMPLOYEES.get(employee_id)
    if employee is None:
        raise ApiNotFound(employee_id)
    return employee.manager_id


# --- справочник ----------------------------------------------------------------------


async def get_employee(employee_id: str) -> Employee:
    """Карточка сотрудника."""
    await _latency()
    employee = EMPLOYEES.get(employee_id)
    if employee is None:
        raise ApiNotFound(employee_id)
    return employee


async def hr_partner(employee_id: str) -> Employee | None:
    """HR-партнёр, закреплённый за сотрудником."""
    employee = await get_employee(employee_id)
    if employee.hr_partner_id is None:
        return None
    return EMPLOYEES.get(employee.hr_partner_id)


async def hr_service_contacts() -> dict[str, str]:
    """Общие контакты кадровой службы."""
    await _latency()
    return dict(HR_SERVICE_CONTACTS)


async def vacation_balance(employee_id: str) -> int:
    """Остаток дней отпуска."""
    employee = await get_employee(employee_id)
    return employee.vacation_days_left


# --- обучение ------------------------------------------------------------------------


async def find_course(name_part: str) -> list[Course]:
    """Курсы, название которых содержит подстроку."""
    await _latency()
    needle = name_part.lower().replace("ё", "е").strip()
    if not needle:
        return []
    return [c for c in COURSES.values() if needle in c.name.lower().replace("ё", "е")]


async def get_course(course_id: int) -> Course:
    """Курс по идентификатору."""
    await _latency()
    course = COURSES.get(course_id)
    if course is None:
        raise ApiNotFound(str(course_id))
    return course


async def training_history(employee_id: str) -> list[TrainingRecord]:
    """История обучения сотрудника."""
    await get_employee(employee_id)
    return [r for r in TRAINING_HISTORY if r.employee_id == employee_id]


async def assignment(employee_id: str, course_id: int) -> Assignment | None:
    """Назначение курса сотруднику, если оно есть."""
    await get_employee(employee_id)
    await get_course(course_id)
    for item in ASSIGNMENTS:
        if item.employee_id == employee_id and item.course_id == course_id:
            return item
    return None


# --- база знаний ---------------------------------------------------------------------


async def search_kb(query: str, limit: int) -> list[tuple[Instruction, float]]:
    """Поиск инструкций по запросу. Стоит на месте pgvector + эмбеддингов GigaChat."""
    await _latency()
    return rank(query, limit)


async def get_instruction(instruction_id: str) -> Instruction:
    """Инструкция по идентификатору."""
    await _latency()
    instruction = INSTRUCTIONS.get(instruction_id)
    if instruction is None:
        raise ApiNotFound(instruction_id)
    return instruction
