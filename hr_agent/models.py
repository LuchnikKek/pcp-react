"""Фабрика модели.

GigaChat: нет параллельных `tool_calls`, structured output медленный (не используем),
штатный tool calling работает.
"""

from langchain_core.language_models import BaseChatModel
from langchain_gigachat.chat_models import GigaChat

from hr_agent.config import Settings, settings


class MissingCredentialsError(RuntimeError):
    """Не задан GIGACHAT_CREDENTIALS."""


def build_model(config: Settings | None = None) -> BaseChatModel:
    """Собрать чат-модель из настроек окружения."""
    config = config or settings
    if not config.gigachat_credentials:
        raise MissingCredentialsError("Не задан GIGACHAT_CREDENTIALS — агента не на чем запускать")
    return GigaChat(
        credentials=config.gigachat_credentials,
        scope=config.gigachat_scope,
        model=config.gigachat_model,
        verify_ssl_certs=config.gigachat_verify_ssl,
        ca_bundle_file=config.gigachat_ca_bundle,
        temperature=config.gigachat_temperature,
        timeout=config.gigachat_timeout,
    )
