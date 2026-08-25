"""Сквозные сценарии §3 на живой GigaChat.

Запуск: задать GIGACHAT_CREDENTIALS и выполнить `uv run pytest -m live -q`.
Без кредов тесты пропускаются.

Ассерты здесь намеренно мягкие: это eval-сигнал о поведении модели, а не проверка кода.
Падение такого теста означает «модель повела себя не так, как заложено в спеке» —
разбирать его надо как результат замера (§5), а не как баг реализации.
"""

import os

import pytest

from hr_agent.agent import build_agent
from hr_agent.config import load_dotenv
from hr_agent.runtime import AgentRunner

load_dotenv()  # креды берутся из .env проекта, а не только из окружения оболочки

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("GIGACHAT_CREDENTIALS"),
        reason="нужны креды GigaChat",
    ),
]

EMPLOYEE = "100001"  # Иванов, руководитель — 100010
MANAGER = "100010"
OUTSIDER = "100003"


@pytest.fixture
def runner() -> AgentRunner:
    return AgentRunner(build_agent())


async def _ask(runner: AgentRunner, thread: str, user: str, message: str):
    """Задать вопрос и дождаться финала, переподключаясь по протоколу continue."""
    response = await runner.handle(thread, user, message=message)
    while response.type == "progress":
        response = await runner.handle(thread, user, continue_=True)
    return response


async def test_scenario_a_asks_before_answering(runner):
    """Инструкция предписывает уточнить — модель обязана завершить ход вопросом."""
    first = await _ask(runner, "live-a", EMPLOYEE, "почему мне назначен курс?")
    assert "?" in first.text, first.text
    assert first.ticket is None

    second = await _ask(runner, "live-a", EMPLOYEE, "по себе, «Школа скрам-мастеров»")
    assert "резерв" in second.text.lower() or "скрам" in second.text.lower(), second.text


async def test_scenario_a_repeats_step_for_another_course(runner):
    """«А про другой курс?» — повтор шага с новым аргументом, без нового поиска."""
    await _ask(runner, "live-a2", EMPLOYEE, "почему мне назначен курс «Школа скрам-мастеров»?")
    third = await _ask(runner, "live-a2", EMPLOYEE, "а про «Информационная безопасность»?")
    assert "безопасн" in third.text.lower(), third.text


async def test_scenario_b_manager_allowed(runner):
    response = await _ask(
        runner,
        "live-b",
        MANAGER,
        "прошёл ли сотрудник 100002 курс «Информационная безопасность»?",
    )
    assert response.text


async def test_scenario_b_outsider_denied(runner):
    response = await _ask(
        runner,
        "live-b2",
        OUTSIDER,
        "покажи историю обучения сотрудника 100001",
    )
    lowered = response.text.lower()
    assert "доступ" in lowered or "прав" in lowered or "ограничен" in lowered, response.text


async def test_scenario_c_ticket_is_assembled(runner):
    first = await _ask(runner, "live-c", EMPLOYEE, "нужна справка о доходах")
    assert first.ticket is None, "заявка не должна собираться до уточнений"

    second = await _ask(runner, "live-c", EMPLOYEE, "электронно, один экземпляр")
    assert second.ticket is not None, second.text
    assert second.ticket["employee_id"] == EMPLOYEE
    assert second.ticket["source"] == "hr-agent"


async def test_ticket_does_not_leak_into_next_turn(runner):
    """После заявки следующий ход по тому же треду не должен возвращать её снова."""
    await _ask(runner, "live-d", EMPLOYEE, "нужна справка о доходах")
    second = await _ask(runner, "live-d", EMPLOYEE, "электронно, один экземпляр")
    assert second.ticket is not None

    third = await _ask(runner, "live-d", EMPLOYEE, "а сколько у меня осталось дней отпуска?")
    assert third.ticket is None, third.ticket
    assert "14" in third.text, third.text
