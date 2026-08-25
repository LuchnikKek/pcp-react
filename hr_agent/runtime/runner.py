"""Обработчик одного HTTP-запроса поверх фонового запуска агента (ARCHITECTURE.md §2.8)."""

import asyncio
import logging
from typing import Any

from langchain_core.messages import HumanMessage

from hr_agent.config import settings
from hr_agent.context import build_context
from hr_agent.prompts import DEFAULT_PROGRESS
from hr_agent.runtime.contracts import AgentResponse, NoActiveRun, RunInProgress
from hr_agent.runtime.registry import RunRegistry

logger = logging.getLogger(__name__)


class AgentRunner:
    """Держит бюджет ответа: HTTP ждёт финал не дольше `response_budget`.

    Не дождались — отдаём последний текст прогресса, а ход продолжает крутиться в фоне;
    фронт перезванивает с `continue=true` и подключается к той же задаче.
    """

    def __init__(
        self,
        agent: Any,
        response_budget: float | None = None,
        hard_limit: float | None = None,
    ) -> None:
        self._agent = agent
        self._budget = settings.response_budget if response_budget is None else response_budget
        self._registry = RunRegistry(settings.run_hard_limit if hard_limit is None else hard_limit)

    async def handle(
        self,
        thread_id: str,
        user_id: str,
        message: str | None = None,
        continue_: bool = False,
    ) -> AgentResponse:
        """Обработать один запрос фронта."""
        run = self._registry.get(thread_id)

        if run is None:
            if continue_ or message is None:
                raise NoActiveRun(thread_id)
            context = await build_context(user_id)
            run = self._registry.start(
                thread_id,
                self._agent,
                # ticket сбрасывается на входе каждого хода: заявка уходит на фронт один раз,
                # иначе она осталась бы в чекпоинте треда и возвращалась в каждом
                # последующем ответе — фронт принял бы её за новую
                {"messages": [HumanMessage(message)], "ticket": None},
                {"configurable": {"thread_id": thread_id}},
                context,
            )
        elif not continue_:
            raise RunInProgress(thread_id)

        try:
            final = await asyncio.wait_for(asyncio.shield(run.task), timeout=self._budget)
        except TimeoutError:
            return AgentResponse(type="progress", text=run.last_progress or DEFAULT_PROGRESS)
        except Exception:
            self._registry.drop(thread_id)
            logger.exception("run failed: thread=%s", thread_id)
            raise

        self._registry.drop(thread_id)
        return AgentResponse(type="final", text=final.text, ticket=final.ticket)

    async def shutdown(self) -> None:
        """Отменить незавершённые ходы — вызывается при остановке приложения."""
        self._registry.cancel_all()
