"""Тесты HTTP-слоя: коды ответов и протокол continue. Агент подменён тем же стабом."""

import pytest
from fastapi.testclient import TestClient

from hr_agent.api import create_app
from hr_agent.runtime import AgentRunner
from tests.test_runtime import StubGraph

USER = "100001"


@pytest.fixture
def client_factory():
    def make(graph: StubGraph, **runner_kwargs) -> TestClient:
        return TestClient(create_app(AgentRunner(graph, **runner_kwargs)))

    return make


def test_health(client_factory):
    with client_factory(StubGraph()) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_final_answer(client_factory):
    with client_factory(StubGraph(answer="Остаток отпуска — 14 дней"), response_budget=5.0) as c:
        response = c.post(
            "/chat", json={"thread_id": "t1", "user_id": USER, "message": "остаток отпуска"}
        )
    assert response.status_code == 200
    assert response.json() == {
        "type": "final",
        "text": "Остаток отпуска — 14 дней",
        "ticket": None,
    }


def test_progress_then_continue(client_factory):
    graph = StubGraph(step_delay=0.05, answer="Ответ готов")
    with client_factory(graph, response_budget=0.06) as client:
        first = client.post(
            "/chat", json={"thread_id": "t2", "user_id": USER, "message": "вопрос"}
        ).json()
        assert first["type"] == "progress"

        while True:
            nxt = client.post(
                "/chat", json={"thread_id": "t2", "user_id": USER, "continue": True}
            ).json()
            if nxt["type"] == "final":
                break

    assert nxt["text"] == "Ответ готов"
    assert graph.starts == 1


def test_new_message_during_run_returns_409(client_factory):
    with client_factory(StubGraph(step_delay=0.05), response_budget=0.06) as client:
        client.post("/chat", json={"thread_id": "t3", "user_id": USER, "message": "первый"})
        conflict = client.post(
            "/chat", json={"thread_id": "t3", "user_id": USER, "message": "второй"}
        )
    assert conflict.status_code == 409


def test_continue_without_run_returns_400(client_factory):
    with client_factory(StubGraph()) as client:
        response = client.post("/chat", json={"thread_id": "t4", "user_id": USER, "continue": True})
    assert response.status_code == 400


def test_unknown_user_returns_404(client_factory):
    with client_factory(StubGraph()) as client:
        response = client.post(
            "/chat", json={"thread_id": "t5", "user_id": "999999", "message": "вопрос"}
        )
    assert response.status_code == 404


def test_ticket_is_returned(client_factory):
    ticket = {"category": "Справки", "employee_id": "100001"}
    graph = StubGraph(answer="Заявка готова", ticket=ticket)
    with client_factory(graph, response_budget=5.0) as client:
        response = client.post(
            "/chat", json={"thread_id": "t6", "user_id": USER, "message": "нужна справка"}
        )
    assert response.json()["ticket"] == ticket
