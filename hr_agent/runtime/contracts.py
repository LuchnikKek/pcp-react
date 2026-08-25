"""Контракт runtime с фронтом (ARCHITECTURE.md §2.8)."""

from typing import Any, Literal

from pydantic import BaseModel


class AgentResponse(BaseModel):
    """Ответ бэкенда на один HTTP-запрос.

    `progress` означает, что ход ещё идёт: фронт показывает текст и перезванивает
    с `continue=true`.
    """

    type: Literal["final", "progress"]
    text: str
    ticket: dict[str, Any] | None = None


class RuntimeConflict(Exception):
    """Базовая ошибка состояния запуска."""


class NoActiveRun(RuntimeConflict):
    """Продолжение запрошено, но активного запуска нет."""


class RunInProgress(RuntimeConflict):
    """Новое сообщение пришло, пока предыдущий ход ещё выполняется."""
