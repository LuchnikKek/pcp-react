"""Runtime-обёртка над агентом (ARCHITECTURE.md §2.8).

Граф про SLA не знает: бюджет ответа, фоновый запуск и ответ типа «прогресс» живут здесь.
"""

from hr_agent.runtime.contracts import AgentResponse, NoActiveRun, RunInProgress
from hr_agent.runtime.runner import AgentRunner

__all__ = ["AgentResponse", "AgentRunner", "NoActiveRun", "RunInProgress"]
