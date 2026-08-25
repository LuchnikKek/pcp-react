# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Статус репозитория

В репозитории **PoC** архитектуры из `ARCHITECTURE.md`. Спека — источник истины по контрактам,
ADR и анти-паттернам; читать её перед задачей. Код реализует её ядро на синтетических данных.

Что настоящее, а что подменено на время PoC:

| Слой | Сейчас |
|---|---|
| Модель | живая GigaChat (`langchain-gigachat`), кредов в репозитории нет |
| БЗ (pgvector + эмбеддинги) | 12 инструкций и лексический скоринг в `hr_agent/synthetic/kb.py` |
| ~20 внутренних API | async-заглушки `hr_agent/synthetic/api.py` с задержкой ~150 мс |
| 40 тулзов | 4 базовых + 6 API-тулзов — представители разных форм сигнатуры |
| Чекпоинтер Postgres | `InMemorySaver` |
| Составные тулзы, `SkillsMiddleware` | не реализованы (фаза 2 — только по результатам eval) |

Python 3.12, пакетный менеджер — `uv` (venv в `.venv`, лок — `uv.lock`). Весь код асинхронный.

```powershell
uv sync                       # зависимости по uv.lock
uv run pytest -q              # 91 тест; live исключены через addopts -m 'not live'
uv run pytest -q tests/test_authz.py::test_stranger_denied   # один тест
uv run pytest -m live -q      # 6 сценариев §3 на живой модели, нужны креды
uv run ruff check --fix       # линтер
uv run ruff format            # форматирование
uv run uvicorn hr_agent.api.app:app --reload   # + requests.http
```

Переменные окружения читаются из `.env` в корне проекта (`load_dotenv` в `config.py`, свой
разбор без зависимостей; уже заданный `$env:VAR` сильнее файла). Шаблон — `.env.example`,
сам `.env` в `.gitignore`. Без `GIGACHAT_CREDENTIALS` приложение падает на старте с
`MissingCredentialsError`, а live-тесты пропускаются.

`ruff` настроен с `ANN` (аннотации типов обязательны), `extend-exclude = ["*.md"]` (иначе
`ruff format` переписывает python-блоки в `ARCHITECTURE.md`) и выключенными `RUF001/002/003`
(проект русскоязычный).

## Структура

```
hr_agent/
  config.py      Settings — все пороги и env в одном месте
  prompts.py     SYSTEM_PROMPT, SUMMARY_PROMPT, PROGRESS_TEXTS
  context.py     RunContext, build_context
  state.py       HRState + HRStateMiddleware (носитель схемы state)
  policy.py      POLICY: тулза → Rule
  models.py      фабрика GigaChat
  agent.py       build_agent — сборка create_agent с порядком middleware из §2.6
  synthetic/     стенд: kb, directory, courses, api  ← единственное, что меняется при переезде
  tools/         types.py (EmployeeRef), base.py (search/get_instruction/find_course/create_ticket),
                 api/training.py, api/staff.py
  middleware/    authz.py, progress.py, dynamic_prompt.py
  runtime/       contracts.py, registry.py, runner.py — SLA, фоновый запуск, progress/continue
  api/app.py     FastAPI: POST /chat, GET /health
```

## Что за система

Агент кадровой поддержки (HR support) на `langchain >= 1.1` / LangGraph:
**один ReAct-агент `create_agent` + middleware**, без графов-роутеров и второго контура.
Модель — GigaChat, БЗ — ~1600 инструкций в pgvector, ~40 читающих тулзов поверх внутренних API.

Ключевые архитектурные инварианты (нарушать нельзя, обоснования — `ARCHITECTURE.md` §1, §7):

- **Вопрос пользователю = завершение хода текстом без `tool_calls`.** Никаких `interrupt()`,
  тулзы `ask_user`, текстовых маркеров, HITL-middleware.
- **Никакого неявного субъекта.** Сотрудник всегда явный параметр типа `EmployeeRef`
  (табельный номер или литерал `"me"`), резолвится внутри тулзы через `ToolRuntime.context`.
  Табельный номер автора никогда не попадает в system prompt.
- **Авторизация — только `AuthzMiddleware` + таблица `POLICY`.** Не моделью, не вручную в тулзах.
  Субъекты извлекаются из `tool_call_schema` по типу `EmployeeRef`, а не по имени параметра
  (`extract_employee_refs` в `tools/types.py`). `AuthzMiddleware` реализует только
  `awrap_tool_call`; синхронный `wrap_tool_call` намеренно падает, чтобы синхронный запуск
  не прошёл мимо проверки прав.
- **Бизнес-правила живут в тексте инструкций БЗ, не в промпте.** System prompt минимальный;
  дублирование правил из БЗ в промпт — ошибка.
- **БЗ не размечается тулзами.** Связка «инструкция → тулза» держится на лексике описаний
  тулзов: описание тулзы обязано содержать те же термины, что и инструкции.
- **Ошибки тулзов возвращаются моделью читаемым текстом**, а не пробрасываются исключением.
- Не использовать structured output / `response_format` (медленный на GigaChat),
  `LLMToolSelectorMiddleware`, кэш результатов тулзов по `(tool, args)`.
- Параллельных `tool_calls` у GigaChat нет — каждый хоп цепочки стоит вызова модели.
  Отсюда `top_text` в `search` (экономит вызов модели) и составные тулзы в фазе 2.

## Два слоя, которые нельзя смешивать

- **Граф (агент)** ничего не знает про SLA и HTTP.
- **Runtime (`runtime/runner.py`)** держит SLA 15 с: агент запускается фоновой `asyncio.Task`,
  HTTP ждёт `RESPONSE_BUDGET=12s`, не дождался — отдаёт ответ `type="progress"` из последнего
  custom-stream события `ProgressMiddleware`; фронт перезванивает с `continue=true` и
  подключается к той же задаче. Жёсткий потолок хода — `RUN_HARD_LIMIT=90s`.
  Сокращать шаги агента ради SLA — не решение.

Заявка (`create_ticket`) — не мутация: схема аргументов тулзы **и есть** форма, отсутствующее
обязательное поле даёт pydantic-ошибку модели, та спрашивает пользователя. Результат кладётся
в `state["ticket"]` через `Command` и уходит на фронт.

**`ticket` сбрасывается в `None` на входе каждого хода** (`runtime/runner.py`). Без этого заявка
остаётся в чекпоинте треда и возвращается в каждом следующем ответе, хотя новую никто не готовил;
поймано на живом прогоне, закрыто тестами в `test_runtime.py` и `test_live_scenarios.py`.

## Работа с langchain API

Сигнатуры middleware менялись между версиями — сверять с установленной через MCP-серверы
`docs-langchain` / `reference-langchain`, а не писать по памяти. Что уже проверено на langchain 1.3
и где спека расходится с реальным API:

- `ModelRequest.override(system_message=SystemMessage(...))` — поля `system_prompt`, как в спеке,
  нет.
- `ToolRuntime` реэкспортируется из `langchain.tools`, живёт в `langgraph.prebuilt.tool_node`.
- Порядок middleware: первый в списке — внешний («first defined = outermost»).
- `@tool(args_schema=...)` **ломает инъекцию `ToolRuntime`** — поля объявлять прямо в сигнатуре
  через `Annotated[..., Field(description=...)]`, как в `create_ticket`.
- `args_schema` содержит инжектируемый `runtime`, а `tool_call_schema` — нет; для авторизации
  и всего, что рассуждает о «том, что заполняет модель», брать `tool_call_schema`.

Метки `[УТОЧНИТЬ]` (`ARCHITECTURE.md` §8) — открытые вопросы к заказчику (формат табельного номера,
поля заявки, пороги, протокол фронта). Не додумывать значения молча: спросить или явно
зафиксировать допущение.

## Тесты

Минимум из `ARCHITECTURE.md` §6 покрыт: матрица `AuthzMiddleware`, `create_ticket` при неполных
полях, `progress`/`continue`/409/hard limit в runtime, `top_text` только при отрыве, кеш
`manager_of`.

Два правила:

- **Фейковой модели в PoC нет.** Единственный тестовый двойник — подставной граф `StubGraph`
  в `tests/test_runtime.py`: он проверяет таймауты runtime, а не поведение модели. Всё, что
  касается поведения модели, живёт в `tests/test_live_scenarios.py` под маркером `live`.
- Падение `live`-теста — это **eval-сигнал** (§5 спеки), а не баг реализации. Разбирать как
  результат замера: менять текст инструкции, описание тулзы или порог, а не подгонять ассерт.
