"""Сборка агента: граф компилируется, тулзы привязаны, промпт собирается динамически.

Модель здесь настоящая (`GigaChat`), но с фиктивными кредами — при конструировании
в сеть она не ходит, а запускать агента этот тест не пытается.
"""

from types import SimpleNamespace

import pytest
from langchain_core.messages import SystemMessage
from langchain_gigachat.chat_models import GigaChat

from hr_agent.agent import build_agent
from hr_agent.config import Settings
from hr_agent.middleware import DynamicPromptMiddleware
from hr_agent.models import MissingCredentialsError, build_model
from hr_agent.prompts import PROGRESS_TEXTS
from hr_agent.tools.api import API_TOOLS
from hr_agent.tools.base import BASE_TOOLS
from tests.conftest import make_context


@pytest.fixture
def offline_model() -> GigaChat:
    return GigaChat(credentials="dummy", scope="GIGACHAT_API_PERS", verify_ssl_certs=False)


def test_graph_compiles(offline_model):
    graph = build_agent(model=offline_model)
    nodes = set(graph.get_graph().nodes)
    assert {"model", "tools"} <= nodes


def test_all_tools_have_progress_text():
    """Каждая тулза должна иметь текст прогресса — иначе фронт увидит заглушку."""
    for tool in [*BASE_TOOLS, *API_TOOLS]:
        assert tool.name in PROGRESS_TEXTS, tool.name


def test_build_model_requires_credentials():
    with pytest.raises(MissingCredentialsError):
        build_model(Settings(gigachat_credentials=None))


def test_build_model_passes_settings_through():
    model = build_model(
        Settings(
            gigachat_credentials="dummy",
            gigachat_model="GigaChat-2-Pro",
            gigachat_verify_ssl=False,
            gigachat_temperature=0.3,
        )
    )
    assert model.model == "GigaChat-2-Pro"
    assert model.verify_ssl_certs is False
    assert model.temperature == 0.3


def test_dynamic_prompt_injects_date_and_role_but_not_employee_id():
    middleware = DynamicPromptMiddleware()
    context = make_context("100001", {"employees", "managers"}, role="руководитель")
    captured: list[SystemMessage] = []

    class Request:
        runtime = SimpleNamespace(context=context)

        def override(self, *, system_message: SystemMessage) -> str:
            captured.append(system_message)
            return "overridden"

    result = middleware.wrap_model_call(Request(), lambda req: req)
    assert result == "overridden"

    prompt = captured[0].text
    assert "2026-08-25" in prompt
    assert "руководитель" in prompt
    assert "100001" not in prompt  # табельный номер автора в промпт не попадает
