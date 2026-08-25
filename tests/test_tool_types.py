import pytest
from langchain.tools import ToolRuntime, tool
from pydantic import BaseModel, ValidationError

from hr_agent.config import settings
from hr_agent.context import RunContext
from hr_agent.tools.types import (
    EmployeeRef,
    _validate_ref,
    extract_employee_refs,
    resolve,
    truncated,
)


class Nested(BaseModel):
    employee_id: EmployeeRef
    comment: str = ""


@tool
async def scalar_tool(employee_id: EmployeeRef, runtime: ToolRuntime[RunContext]) -> str:
    """Тулза с одним субъектом."""
    return employee_id


@tool
async def list_tool(employee_ids: list[EmployeeRef], course_id: int) -> str:
    """Тулза со списком субъектов."""
    return str(employee_ids)


@tool
async def nested_tool(payload: Nested) -> str:
    """Тулза с субъектом во вложенной модели."""
    return payload.employee_id


@tool
async def optional_tool(course_id: int, employee_id: EmployeeRef | None = None) -> str:
    """Тулза с необязательным субъектом."""
    return str(employee_id)


@tool
async def subjectless_tool(course_id: int) -> str:
    """Тулза без субъектов."""
    return str(course_id)


@pytest.mark.parametrize("value", ["me", "100001", "999999"])
def test_valid_refs(value):
    assert _validate_ref(value) == value


@pytest.mark.parametrize(
    "value",
    ["", "10001", "1000010", "me ", "ME", "abc", "100 001", "табельный 100001", "me,100001"],
)
def test_invalid_refs(value):
    with pytest.raises(ValueError, match="Ожидается табельный номер"):
        _validate_ref(value)


def test_ref_validated_inside_model():
    assert Nested(employee_id="me").employee_id == "me"
    with pytest.raises(ValidationError):
        Nested(employee_id="сотрудник Иванов")


def test_resolve():
    assert resolve("me", "100001") == "100001"
    assert resolve("100002", "100001") == "100002"


def test_extract_scalar():
    assert extract_employee_refs(scalar_tool, {"employee_id": "100001"}) == ["100001"]


def test_extract_list():
    args = {"employee_ids": ["100001", "me", "100002"], "course_id": 17}
    assert extract_employee_refs(list_tool, args) == ["100001", "me", "100002"]


def test_extract_nested():
    args = {"payload": {"employee_id": "100003", "comment": "проверка"}}
    assert extract_employee_refs(nested_tool, args) == ["100003"]


def test_extract_optional_absent_and_present():
    assert extract_employee_refs(optional_tool, {"course_id": 17}) == []
    assert extract_employee_refs(optional_tool, {"course_id": 17, "employee_id": "me"}) == ["me"]


def test_extract_subjectless():
    assert extract_employee_refs(subjectless_tool, {"course_id": 17}) == []


def test_extract_ignores_runtime_and_other_params():
    """runtime инжектируется и в схеме вызова не участвует, course_id — не субъект."""
    assert "runtime" in scalar_tool.args_schema.model_fields
    assert "runtime" not in scalar_tool.tool_call_schema.model_fields
    assert extract_employee_refs(scalar_tool, {"employee_id": "me", "runtime": object()}) == ["me"]
    assert extract_employee_refs(list_tool, {"employee_ids": [], "course_id": 17}) == []


def test_extract_dedupes():
    args = {"employee_ids": ["100001", "100001"], "course_id": 1}
    assert extract_employee_refs(list_tool, args) == ["100001"]


def test_truncated():
    items = [{"id": i} for i in range(settings.max_items + 3)]
    result = truncated({"courses": items}, key="courses")
    assert len(result["courses"]) == settings.max_items
    assert result["truncated"] is True

    short = {"courses": items[:2]}
    assert truncated(short, key="courses") == short
