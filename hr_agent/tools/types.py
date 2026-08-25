"""Общие типы и хелперы тулзов (ARCHITECTURE.md §2.3).

Ключевое здесь — `EmployeeRef`. Он одновременно:
- валидирует вход (табельный номер или литерал "me");
- служит меткой, по которой `AuthzMiddleware` находит субъектов вызова — по типу параметра,
  а не по его имени.
"""

import re
import types
import typing
from dataclasses import dataclass
from typing import Annotated, Any, get_args, get_origin, get_type_hints

from langchain_core.tools import BaseTool
from pydantic import AfterValidator, BaseModel

from hr_agent.config import settings

EMPLOYEE_ID_RE = re.compile(r"^\d{6}$")  # [УТОЧНИТЬ] формат табельного номера
SELF_REF = "me"


@dataclass(frozen=True)
class _EmployeeRefMarker:
    """Метка в Annotated: делает параметр видимым для AuthzMiddleware."""


def _validate_ref(value: str) -> str:
    if value == SELF_REF or EMPLOYEE_ID_RE.fullmatch(value):
        return value
    raise ValueError(f'Ожидается табельный номер из 6 цифр или "me", получено: {value!r}')


EmployeeRef = Annotated[str, AfterValidator(_validate_ref), _EmployeeRefMarker()]


def resolve(ref: str, author_id: str) -> str:
    """Развернуть псевдоним автора в табельный номер."""
    return author_id if ref == SELF_REF else ref


def tool_error(message: str) -> str:
    """Ошибка, возвращаемая модели текстом, а не исключением наружу."""
    return f"Ошибка: {message}"


def truncated(payload: dict[str, Any], key: str) -> dict[str, Any]:
    """Обрезать список в payload до MAX_ITEMS, пометив факт усечения."""
    items = payload.get(key)
    if not isinstance(items, list) or len(items) <= settings.max_items:
        return payload
    return {**payload, key: items[: settings.max_items], "truncated": True}


def _is_employee_ref(annotation: Any) -> bool:
    return any(isinstance(meta, _EmployeeRefMarker) for meta in get_args(annotation)[1:])


def _collect(annotation: Any, value: Any, found: list[str]) -> None:
    if value is None:
        return

    origin = get_origin(annotation)

    if origin is Annotated:
        if _is_employee_ref(annotation):
            if isinstance(value, str):
                found.append(value)
            return
        _collect(get_args(annotation)[0], value, found)
        return

    if origin in (typing.Union, types.UnionType):
        for arg in get_args(annotation):
            if arg is not types.NoneType:
                _collect(arg, value, found)
        return

    if origin in (list, set, tuple, frozenset):
        args = get_args(annotation)
        if not args or not isinstance(value, list | tuple | set | frozenset):
            return
        for item in value:
            _collect(args[0], item, found)
        return

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if isinstance(value, BaseModel):
            value = value.model_dump()
        if isinstance(value, dict):
            for name, hint in get_type_hints(annotation, include_extras=True).items():
                _collect(hint, value.get(name), found)


def extract_employee_refs(tool: BaseTool, args: dict[str, Any]) -> list[str]:
    """Все значения параметров типа EmployeeRef в аргументах вызова, включая вложенные.

    Обход идёт по схеме аргументов тулзы, а не по значениям: параметр опознаётся по типу,
    поэтому переименование аргумента не ломает авторизацию.

    Берём `tool_call_schema` — схему, которую заполняет модель. В `args_schema` дополнительно
    лежат инжектируемые параметры (`runtime`), которые модель не видит.
    """
    schema = getattr(tool, "tool_call_schema", None) or getattr(tool, "args_schema", None)
    if not (isinstance(schema, type) and issubclass(schema, BaseModel)):
        return []

    found: list[str] = []
    for name, hint in get_type_hints(schema, include_extras=True).items():
        _collect(hint, args.get(name), found)
    return list(dict.fromkeys(found))
