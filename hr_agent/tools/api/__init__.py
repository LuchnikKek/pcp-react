"""Тулзы поверх внутренних API, сгруппированные по доменам.

В PoC их 6 — представители разных форм сигнатуры (скаляр `EmployeeRef`, список,
без субъекта), чтобы было на чём проверять авторизацию и контракт §2.3.
"""

from hr_agent.tools.api.staff import (
    get_hr_partner,
    get_hr_service_contacts,
    get_vacation_balance,
)
from hr_agent.tools.api.training import (
    compare_training,
    get_assignment,
    get_training_history,
)

API_TOOLS = [
    get_training_history,
    get_assignment,
    compare_training,
    get_hr_partner,
    get_vacation_balance,
    get_hr_service_contacts,
]

__all__ = [
    "API_TOOLS",
    "compare_training",
    "get_assignment",
    "get_hr_partner",
    "get_hr_service_contacts",
    "get_training_history",
    "get_vacation_balance",
]
