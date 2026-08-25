import pytest
from langchain_core.messages import ToolMessage

from hr_agent.middleware.authz import AuthzMiddleware, ManagerCache
from hr_agent.policy import POLICY, Rule
from hr_agent.synthetic import api
from hr_agent.tools.api import (
    compare_training,
    get_hr_partner,
    get_hr_service_contacts,
    get_training_history,
    get_vacation_balance,
)
from tests.conftest import make_context, make_tool_request

SELF = "100001"  # Иванов, руководитель — 100010
SUBORDINATE = "100002"  # Петрова, руководитель — 100010
STRANGER = "100003"  # Николаев, руководитель — 100011

AUTHOR = make_context(SELF, {"employees"})
MANAGER = make_context("100010", {"employees", "managers"}, role="руководитель")
HR = make_context("100020", {"employees", "hr"}, role="HR-партнёр")
LEARNING = make_context("100030", {"employees", "l&d"}, role="специалист по обучению")
OUTSIDER = make_context(STRANGER, {"employees"})


async def _run(middleware: AuthzMiddleware, tool, args, context):
    """Пропустить вызов через middleware. handler возвращает маркер «дошло до тулзы»."""
    request = make_tool_request(tool, args, context)

    async def handler(req):
        return ToolMessage(content="EXECUTED", tool_call_id=req.tool_call["id"])

    return await middleware.awrap_tool_call(request, handler)


def _executed(result: ToolMessage) -> bool:
    return result.content == "EXECUTED"


@pytest.fixture
def authz() -> AuthzMiddleware:
    return AuthzMiddleware()


# --- матрица {кто спрашивает} × {правило} --------------------------------------------


async def test_self_always_allowed(authz):
    """Про себя можно всё — и через "me", и по своему табельному номеру."""
    assert _executed(await _run(authz, get_hr_partner, {"employee_id": "me"}, AUTHOR))
    assert _executed(await _run(authz, get_hr_partner, {"employee_id": SELF}, AUTHOR))


async def test_group_grants_access_to_others(authz):
    assert _executed(await _run(authz, get_training_history, {"employee_id": STRANGER}, HR))
    assert _executed(await _run(authz, get_training_history, {"employee_id": STRANGER}, LEARNING))


async def test_manager_grants_access_to_subordinate(authz):
    assert _executed(await _run(authz, get_training_history, {"employee_id": SUBORDINATE}, MANAGER))


async def test_manager_denied_for_alien_employee(authz):
    """Руководитель — но не этого сотрудника."""
    result = await _run(authz, get_training_history, {"employee_id": STRANGER}, MANAGER)
    assert result.status == "error"
    assert STRANGER in result.content


async def test_stranger_denied(authz):
    result = await _run(authz, get_training_history, {"employee_id": SELF}, OUTSIDER)
    assert result.status == "error"
    assert not _executed(result)


async def test_default_rule_allows_only_self(authz):
    """get_hr_partner — DEFAULT_RULE: даже HR и руководитель не могут по чужому."""
    assert POLICY["get_hr_partner"] == Rule()
    for context in (HR, MANAGER):
        result = await _run(authz, get_hr_partner, {"employee_id": SUBORDINATE}, context)
        assert result.status == "error"


async def test_group_rule_is_specific(authz):
    """get_vacation_balance разрешён hr, но не l&d."""
    assert _executed(await _run(authz, get_vacation_balance, {"employee_id": STRANGER}, HR))
    denied = await _run(authz, get_vacation_balance, {"employee_id": STRANGER}, LEARNING)
    assert denied.status == "error"


async def test_tool_without_subject_skips_policy(authz):
    assert _executed(await _run(authz, get_hr_service_contacts, {}, OUTSIDER))


async def test_list_subject_denied_on_any_alien_member(authz):
    args = {"employee_ids": ["me", SUBORDINATE], "course_ids": [19]}
    assert _executed(await _run(authz, compare_training, args, MANAGER))

    denied = await _run(authz, compare_training, args, AUTHOR)
    assert denied.status == "error"
    assert SUBORDINATE in denied.content


# --- кеш manager_of -------------------------------------------------------------------


async def test_manager_cache_calls_api_once_per_pair(monkeypatch):
    calls: list[str] = []

    async def spy(employee_id: str) -> str | None:
        calls.append(employee_id)
        return {"100002": "100010", "100003": "100011"}.get(employee_id)

    monkeypatch.setattr(api, "manager_of", spy)
    authz = AuthzMiddleware(manager_cache=ManagerCache(ttl=60.0))

    for _ in range(3):
        await _run(authz, get_training_history, {"employee_id": SUBORDINATE}, MANAGER)
    assert calls == [SUBORDINATE]

    await _run(authz, get_training_history, {"employee_id": STRANGER}, MANAGER)
    assert calls == [SUBORDINATE, STRANGER]


async def test_manager_cache_expires(monkeypatch):
    calls: list[str] = []

    async def spy(employee_id: str) -> str | None:
        calls.append(employee_id)
        return "100010"

    monkeypatch.setattr(api, "manager_of", spy)
    authz = AuthzMiddleware(manager_cache=ManagerCache(ttl=0.0))

    await _run(authz, get_training_history, {"employee_id": SUBORDINATE}, MANAGER)
    await _run(authz, get_training_history, {"employee_id": SUBORDINATE}, MANAGER)
    assert calls == [SUBORDINATE, SUBORDINATE]


# --- fail-closed ----------------------------------------------------------------------


def test_sync_path_refuses_to_run(authz):
    """Синхронный запуск не должен молча пройти мимо проверки прав."""
    request = make_tool_request(get_training_history, {"employee_id": STRANGER}, OUTSIDER)
    with pytest.raises(RuntimeError, match="асинхронном запуске"):
        authz.wrap_tool_call(request, lambda req: None)
