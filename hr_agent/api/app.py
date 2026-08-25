"""FastAPI-приложение PoC.

Тонкий транспорт: вся логика хода и SLA — в `hr_agent.runtime`. Чтобы встроить агента в
существующий бэкенд, достаточно перенести содержимое ручки `/chat`.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from hr_agent.agent import build_agent
from hr_agent.runtime import AgentResponse, AgentRunner, NoActiveRun, RunInProgress
from hr_agent.synthetic.api import ApiNotFound


class ChatRequest(BaseModel):
    """Запрос фронта на один ход диалога."""

    model_config = ConfigDict(populate_by_name=True)

    thread_id: str = Field(description="Идентификатор диалога, он же ключ чекпоинта")
    user_id: str = Field(description="Табельный номер автора обращения")
    message: str | None = Field(default=None, description="Сообщение пользователя")
    continue_: bool = Field(
        default=False,
        alias="continue",
        description="Подключиться к уже идущему ходу вместо старта нового",
    )


def create_app(runner: AgentRunner | None = None) -> FastAPI:
    """Собрать приложение. Готовый `runner` можно передать снаружи — например, в тестах."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.runner = runner or AgentRunner(build_agent())
        try:
            yield
        finally:
            await app.state.runner.shutdown()

    application = FastAPI(title="HR support agent (PoC)", lifespan=lifespan)

    def get_runner(request: Request) -> AgentRunner:
        return request.app.state.runner

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/chat", response_model=AgentResponse)
    async def chat(
        body: ChatRequest,
        agent_runner: Annotated[AgentRunner, Depends(get_runner)],
    ) -> AgentResponse:
        try:
            return await agent_runner.handle(
                thread_id=body.thread_id,
                user_id=body.user_id,
                message=body.message,
                continue_=body.continue_,
            )
        except RunInProgress as exc:
            raise HTTPException(
                status_code=409,
                detail="По этому диалогу уже выполняется ход; дождитесь ответа",
            ) from exc
        except NoActiveRun as exc:
            raise HTTPException(
                status_code=400,
                detail="Активного хода нет: пришлите message без continue",
            ) from exc
        except ApiNotFound as exc:
            raise HTTPException(
                status_code=404,
                detail=f"Сотрудник {body.user_id} не найден",
            ) from exc

    return application


app = create_app()
