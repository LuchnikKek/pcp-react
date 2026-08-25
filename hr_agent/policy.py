"""Таблица прав: тулза → правило (ARCHITECTURE.md §2.6).

Право проверяется только для субъектов, отличных от автора обращения. Тулза, у которой нет
параметров типа `EmployeeRef`, проверку проходит без обращения к таблице.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    """Правило доступа к данным по чужому сотруднику."""

    groups: frozenset[str] = frozenset()
    """Любая из групп даёт право вызывать тулзу по другим людям."""

    manager_ok: bool = False
    """Руководитель субъекта имеет право."""


DEFAULT_RULE = Rule()
"""Тулза без записи в POLICY — только про себя."""

_TRAINING_GROUPS = frozenset({"hr", "l&d"})

POLICY: dict[str, Rule] = {
    "get_training_history": Rule(groups=_TRAINING_GROUPS, manager_ok=True),
    "get_assignment": Rule(groups=_TRAINING_GROUPS, manager_ok=True),
    "compare_training": Rule(groups=_TRAINING_GROUPS, manager_ok=True),
    "get_vacation_balance": Rule(groups=frozenset({"hr"}), manager_ok=True),
    "get_hr_partner": DEFAULT_RULE,  # только про себя
    "create_ticket": Rule(groups=frozenset({"hr"}), manager_ok=False),
}
