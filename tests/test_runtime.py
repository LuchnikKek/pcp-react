"""Тесты бюджета SLA и протокола progress/continue.

Здесь единственный тестовый двойник в PoC — подставной граф вместо агента: проверяются
таймауты runtime, а не поведение модели. Настоящий агент в этих тестах не участвует
осознанно: бюджет в 12 секунд иначе пришлось бы выжидать вживую.
"""

import asyncio

import pytest

from hr_agent.runtime import AgentResponse, AgentRunner, NoActiveRun, RunInProgress
from hr_agent.runtime.registry import EMPTY_ANSWER_TEXT, HARD_LIMIT_TEXT

USER = "100001"
THREAD = "thread-1"


class StubGraph:
    """Граф, который отдаёт заданные события с заданными задержками."""

    def __init__(
        self,
        answer: str = "Готово",
        step_delay: float = 0.0,
        progress: tuple[str, ...] = ("Ищу подходящую инструкцию…",),
        ticket: dict | None = None,
        fail_with: Exception | None = None,
    ) -> None:
        self.answer = answer
        self.step_delay = step_delay
        self.progress = progress
        self.ticket = ticket
        self.fail_with = fail_with
        self.starts = 0
        self.inputs: list[dict] = []

    async def astream(self, agent_input, config, context, stream_mode):
        self.starts += 1
        self.inputs.append(agent_input)
        if self.fail_with is not None:
            raise self.fail_with
        for text in self.progress:
            await asyncio.sleep(self.step_delay)
            yield "custom", {"progress": text}
        await asyncio.sleep(self.step_delay)
        values = {"messages": [_ai(self.answer)]}
        if self.ticket is not None:
            values["ticket"] = self.ticket
        yield "values", values


def _ai(text: str):
    from langchain_core.messages import AIMessage

    return AIMessage(text)


async def test_fast_run_returns_final():
    runner = AgentRunner(StubGraph(answer="Остаток отпуска — 14 дней"), response_budget=5.0)
    result = await runner.handle(THREAD, USER, message="сколько у меня дней отпуска")
    assert result == AgentResponse(type="final", text="Остаток отпуска — 14 дней")


async def test_budget_exceeded_returns_last_progress():
    graph = StubGraph(
        step_delay=0.05,
        progress=("Ищу подходящую инструкцию…", "Считаю остаток отпуска…"),
    )
    runner = AgentRunner(graph, response_budget=0.12)

    first = await runner.handle(THREAD, USER, message="вопрос")
    assert first.type == "progress"
    assert first.text in graph.progress


async def test_continue_attaches_to_same_run():
    graph = StubGraph(step_delay=0.05, answer="Ответ готов")
    runner = AgentRunner(graph, response_budget=0.06)

    first = await runner.handle(THREAD, USER, message="вопрос")
    assert first.type == "progress"

    while True:
        nxt = await runner.handle(THREAD, USER, continue_=True)
        if nxt.type == "final":
            break

    assert nxt.text == "Ответ готов"
    assert graph.starts == 1  # ход не перезапускался


async def test_new_message_while_running_conflicts():
    runner = AgentRunner(StubGraph(step_delay=0.05), response_budget=0.06)
    first = await runner.handle(THREAD, USER, message="первый вопрос")
    assert first.type == "progress"

    with pytest.raises(RunInProgress):
        await runner.handle(THREAD, USER, message="второй вопрос")


async def test_continue_without_active_run():
    runner = AgentRunner(StubGraph())
    with pytest.raises(NoActiveRun):
        await runner.handle(THREAD, USER, continue_=True)


async def test_empty_message_without_active_run():
    runner = AgentRunner(StubGraph())
    with pytest.raises(NoActiveRun):
        await runner.handle(THREAD, USER, message=None)


async def test_hard_limit_cancels_run():
    runner = AgentRunner(StubGraph(step_delay=0.3), response_budget=1.0, hard_limit=0.1)
    result = await runner.handle(THREAD, USER, message="вопрос")
    assert result == AgentResponse(type="final", text=HARD_LIMIT_TEXT)


async def test_ticket_reaches_response():
    ticket = {"category": "Справки", "employee_id": "100001"}
    runner = AgentRunner(StubGraph(answer="Заявка готова", ticket=ticket), response_budget=5.0)
    result = await runner.handle(THREAD, USER, message="нужна справка")
    assert result.ticket == ticket


async def test_run_without_ai_message_falls_back():
    class Silent(StubGraph):
        async def astream(self, agent_input, config, context, stream_mode):
            yield "values", {"messages": []}

    runner = AgentRunner(Silent(), response_budget=5.0)
    result = await runner.handle(THREAD, USER, message="вопрос")
    assert result.text == EMPTY_ANSWER_TEXT


async def test_failed_run_is_dropped_and_reraised():
    runner = AgentRunner(StubGraph(fail_with=ValueError("API упал")), response_budget=5.0)
    with pytest.raises(ValueError, match="API упал"):
        await runner.handle(THREAD, USER, message="вопрос")

    # реестр очищен: следующий вопрос стартует новый ход, а не упирается в 409
    runner._agent = StubGraph(answer="Теперь работает")
    result = await runner.handle(THREAD, USER, message="вопрос")
    assert result.type == "final"


async def test_unknown_user_fails_before_run():
    runner = AgentRunner(StubGraph())
    with pytest.raises(Exception, match="999999"):
        await runner.handle(THREAD, "999999", message="вопрос")


async def test_shutdown_cancels_active_runs():
    graph = StubGraph(step_delay=0.5)
    runner = AgentRunner(graph, response_budget=0.05)
    first = await runner.handle(THREAD, USER, message="вопрос")
    assert first.type == "progress"

    await runner.shutdown()
    with pytest.raises(NoActiveRun):
        await runner.handle(THREAD, USER, continue_=True)


async def test_ticket_is_reset_on_every_new_turn():
    """Заявка из прошлого хода не должна возвращаться снова: на входе ticket сбрасывается.

    Регрессия: без сброса ticket оседает в чекпоинте треда и приезжает в каждом
    последующем ответе, хотя новую заявку никто не готовил.
    """
    graph = StubGraph(answer="Готово")
    runner = AgentRunner(graph, response_budget=5.0)

    await runner.handle(THREAD, USER, message="нужна справка")
    await runner.handle(THREAD, USER, message="а сколько дней отпуска?")

    assert [i["ticket"] for i in graph.inputs] == [None, None]
    assert all("messages" in i for i in graph.inputs)
