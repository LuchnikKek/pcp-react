"""Контекст запуска агента (ARCHITECTURE.md §2.1).

Собирается до запуска агента. В system prompt попадают только `today` и `role` —
табельный номер автора в текст не попадает никогда.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict

from hr_agent.synthetic import api

_ROLE_BY_GROUP: tuple[tuple[str, str], ...] = (
    ("hr", "HR-партнёр"),
    ("l&d", "специалист по обучению"),
    ("managers", "руководитель"),
)
_DEFAULT_ROLE = "сотрудник"


class RunContext(BaseModel):
    """Статический контекст одного запуска агента."""

    model_config = ConfigDict(frozen=True)

    author_id: str
    groups: frozenset[str]
    role: str
    today: date


def derive_role(groups: frozenset[str]) -> str:
    """Человекочитаемая роль для промпта. Порядок важен: первая совпавшая группа выигрывает."""
    for group, role in _ROLE_BY_GROUP:
        if group in groups:
            return role
    return _DEFAULT_ROLE


async def build_context(user_id: str, today: date | None = None) -> RunContext:
    """Собрать контекст: группы из авторизационного эндпоинта, роль — производная от групп."""
    groups = await api.get_groups(user_id)
    return RunContext(
        author_id=user_id,
        groups=groups,
        role=derive_role(groups),
        today=today or date.today(),
    )
