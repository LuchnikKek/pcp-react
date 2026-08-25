"""Курсы, назначения и история обучения."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Course:
    """Курс из каталога обучения."""

    id: int
    name: str


@dataclass(frozen=True)
class Assignment:
    """Назначение курса сотруднику."""

    employee_id: str
    course_id: int
    reason: str
    assigned_by_id: str
    assigned_at: date
    due_at: date


@dataclass(frozen=True)
class TrainingRecord:
    """Запись в истории обучения."""

    employee_id: str
    course_id: int
    status: str  # "completed" | "in_progress" | "not_started"
    finished_at: date | None


COURSES: dict[int, Course] = {
    17: Course(id=17, name="Школа скрам-мастеров"),
    18: Course(id=18, name="Основы Agile"),
    19: Course(id=19, name="Информационная безопасность: базовый курс"),
    20: Course(id=20, name="Управление командой"),
    21: Course(id=21, name="Excel для аналитика"),
    22: Course(id=22, name="Основы бережливого производства"),
}

ASSIGNMENTS: list[Assignment] = [
    Assignment(
        employee_id="100001",
        course_id=17,
        reason="Включён в кадровый резерв на роль скрам-мастера, курс обязателен по плану развития",
        assigned_by_id="100010",
        assigned_at=date(2026, 6, 1),
        due_at=date(2026, 9, 30),
    ),
    Assignment(
        employee_id="100001",
        course_id=19,
        reason="Ежегодное обязательное обучение по информационной безопасности",
        assigned_by_id="100020",
        assigned_at=date(2026, 1, 15),
        due_at=date(2026, 12, 31),
    ),
    Assignment(
        employee_id="100002",
        course_id=18,
        reason="Переход команды на Agile-процессы",
        assigned_by_id="100010",
        assigned_at=date(2026, 5, 20),
        due_at=date(2026, 8, 31),
    ),
    Assignment(
        employee_id="100010",
        course_id=20,
        reason="Развитие управленческих компетенций по итогам оценки",
        assigned_by_id="100020",
        assigned_at=date(2026, 3, 10),
        due_at=date(2026, 10, 1),
    ),
]

TRAINING_HISTORY: list[TrainingRecord] = [
    TrainingRecord("100001", 19, "completed", date(2026, 3, 4)),
    TrainingRecord("100001", 21, "completed", date(2025, 11, 20)),
    TrainingRecord("100001", 17, "in_progress", None),
    TrainingRecord("100002", 19, "completed", date(2026, 2, 18)),
    TrainingRecord("100002", 18, "not_started", None),
    TrainingRecord("100003", 19, "completed", date(2026, 4, 2)),
    TrainingRecord("100003", 22, "completed", date(2026, 5, 30)),
    TrainingRecord("100010", 20, "in_progress", None),
    TrainingRecord("100010", 19, "completed", date(2026, 1, 29)),
]
