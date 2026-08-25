"""Пороги и параметры запуска. Всё, что калибруется по eval, живёт здесь.

Значения, помеченные в ARCHITECTURE.md §8 как [УТОЧНИТЬ], для PoC заданы правдоподобными
синтетическими величинами — заменяются в одном месте.
"""

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOTENV_PATH = PROJECT_ROOT / ".env"


def load_dotenv(path: Path | None = None, *, override: bool = False) -> list[str]:
    """Подгрузить переменные из `.env` в окружение процесса.

    Формат: `KEY=VALUE`, по строке на переменную; пустые строки и `#`-комментарии
    игнорируются, необязательный префикс `export` срезается, обрамляющие кавычки снимаются.
    Значение не разбирается дальше — в нём могут быть любые символы, включая `#`.

    Уже заданные переменные окружения по умолчанию не перетираются: явный `$env:VAR`
    сильнее файла. Возвращает имена применённых переменных — не значения.
    """
    dotenv = path or DOTENV_PATH
    if not dotenv.is_file():
        return []

    applied: list[str] = []
    for raw_line in dotenv.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if override or key not in os.environ:
            os.environ[key] = value
            applied.append(key)
    return applied


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    return raw.strip().lower() in {"1", "true", "yes"} if raw else default


@dataclass(frozen=True)
class Settings:
    """Конфигурация PoC."""

    # search: минимальный относительный отрыв топ-кандидата, при котором отдаём его текст сразу
    gap_threshold: float = 0.25
    # усечение списков в ответах тулзов
    max_items: int = 10

    # контекст
    ctx_edit_trigger: int = 6_000  # токенов, порог ClearToolUsesEdit
    ctx_edit_keep: int = 6  # последних результатов тулзов сохраняем
    summary_trigger: int = 12_000  # токенов, порог SummarizationMiddleware
    summary_keep_messages: int = 40
    model_call_limit: int = 10  # вызовов модели на один запуск

    # SLA (ARCHITECTURE.md §2.8)
    response_budget: float = 12.0  # сколько ждём финал, прежде чем отдать "прогресс"
    run_hard_limit: float = 90.0  # потолок хода, после которого задача отменяется

    # авторизация
    manager_cache_ttl: float = 300.0

    # синтетический стенд: задержка заглушек внутренних API
    synthetic_latency: float = 0.15

    # GigaChat
    gigachat_credentials: str | None = None
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_model: str = "GigaChat-2-Max"
    gigachat_verify_ssl: bool = True
    gigachat_ca_bundle: str | None = None
    gigachat_temperature: float = 0.1
    gigachat_timeout: float = 60.0


def load_settings(*, use_dotenv: bool = True) -> Settings:
    """Собрать настройки из окружения, предварительно подтянув `.env`."""
    if use_dotenv:
        load_dotenv()
    return Settings(
        gap_threshold=_env_float("HR_GAP_THRESHOLD", 0.25),
        max_items=_env_int("HR_MAX_ITEMS", 10),
        ctx_edit_trigger=_env_int("HR_CTX_EDIT_TRIGGER", 6_000),
        summary_trigger=_env_int("HR_SUMMARY_TRIGGER", 12_000),
        model_call_limit=_env_int("HR_MODEL_CALL_LIMIT", 10),
        response_budget=_env_float("HR_RESPONSE_BUDGET", 12.0),
        run_hard_limit=_env_float("HR_RUN_HARD_LIMIT", 90.0),
        synthetic_latency=_env_float("HR_SYNTHETIC_LATENCY", 0.15),
        gigachat_credentials=os.environ.get("GIGACHAT_CREDENTIALS"),
        gigachat_scope=os.environ.get("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"),
        gigachat_model=os.environ.get("GIGACHAT_MODEL", "GigaChat-2-Max"),
        gigachat_verify_ssl=_env_bool("GIGACHAT_VERIFY_SSL", True),
        gigachat_ca_bundle=os.environ.get("GIGACHAT_CA_BUNDLE"),
        gigachat_temperature=_env_float("GIGACHAT_TEMPERATURE", 0.1),
        gigachat_timeout=_env_float("GIGACHAT_TIMEOUT", 60.0),
    )


settings = load_settings()
