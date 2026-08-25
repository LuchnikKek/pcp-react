"""HTTP-транспорт. Логики нет: ручка только вызывает runtime и раскладывает ошибки по кодам."""

from hr_agent.api.app import ChatRequest, app, create_app

__all__ = ["ChatRequest", "app", "create_app"]
