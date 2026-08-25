"""Реестр активных запусков агента: один активный ход на тред (ARCHITECTURE.md §2.8)."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage

from hr_agent.prompts import DEFAULT_PROGRESS

logger = logging.getLogger(__name__)

HARD_LIMIT_TEXT = "Не удалось завершить обработку, попробуйте переформулировать вопрос."
EMPTY_ANSWER_TEXT = "Не удалось сформировать ответ, попробуйте переформулировать вопрос."


@dataclass(frozen=True)
class FinalResult:
    """Итог хода агента."""

    text: str
    ticket: dict[str, Any] | None = None


@dataclass
class Run:
    """Фоновый запуск агента по одному треду."""

    thread_id: str
    task: asyncio.Task[FinalResult]
    last_progress: str | None = field(default=None)


def _final_text(values: dict[str, Any] | None) -> str:
    if not values:
        return EMPTY_ANSWER_TEXT
    for message in reversed(values.get("messages", [])):
        if isinstance(message, AIMessage) and message.text:
            return message.text
    return EMPTY_ANSWER_TEXT


class RunRegistry:
    """Хранит активные запуски и разводит их по `thread_id`."""

    def __init__(self, hard_limit: float) -> None:
        self._hard_limit = hard_limit
        self._runs: dict[str, Run] = {}

    def get(self, thread_id: str) -> Run | None:
        return self._runs.get(thread_id)

    def drop(self, thread_id: str) -> None:
        self._runs.pop(thread_id, None)

    def cancel_all(self) -> None:
        """Отменить все незавершённые ходы и очистить реестр."""
        for run in self._runs.values():
            if not run.task.done():
                run.task.cancel()
        self._runs.clear()

    def start(
        self,
        thread_id: str,
        agent: Any,
        agent_input: dict[str, Any],
        config: dict[str, Any],
        context: Any,
    ) -> Run:
        """Запустить ход в фоне и вернуть запись реестра."""
        run = Run(thread_id=thread_id, task=None)  # type: ignore[arg-type]
        run.task = asyncio.create_task(
            self._execute(run, agent, agent_input, config, context),
            name=f"hr-agent-run:{thread_id}",
        )
        self._runs[thread_id] = run
        return run

    async def _execute(
        self,
        run: Run,
        agent: Any,
        agent_input: dict[str, Any],
        config: dict[str, Any],
        context: Any,
    ) -> FinalResult:
        try:
            return await asyncio.wait_for(
                self._stream(run, agent, agent_input, config, context),
                timeout=self._hard_limit,
            )
        except TimeoutError:
            logger.error(
                "run hard limit exceeded: thread=%s limit=%.1fs", run.thread_id, self._hard_limit
            )
            return FinalResult(text=HARD_LIMIT_TEXT)

    async def _stream(
        self,
        run: Run,
        agent: Any,
        agent_input: dict[str, Any],
        config: dict[str, Any],
        context: Any,
    ) -> FinalResult:
        """Прочитать поток агента: custom-события — прогресс, values — итоговый снапшот."""
        last_values: dict[str, Any] | None = None
        async for mode, chunk in agent.astream(
            agent_input,
            config=config,
            context=context,
            stream_mode=["custom", "values"],
        ):
            if mode == "custom":
                progress = chunk.get("progress") if isinstance(chunk, dict) else None
                run.last_progress = progress or DEFAULT_PROGRESS
            elif mode == "values":
                last_values = chunk

        return FinalResult(
            text=_final_text(last_values),
            ticket=(last_values or {}).get("ticket"),
        )
