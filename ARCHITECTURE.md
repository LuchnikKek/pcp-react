# HR Support Agent — архитектура для реализации

Документ для coding-агента. Описывает целевую архитектуру, контракты и порядок работ.
Всё, что помечено `[ВЕРИФИЦИРОВАТЬ]`, нужно сверить с установленной версией `langchain` (>= 1.1) через
документацию, а не реализовывать по памяти — сигнатуры middleware менялись между версиями.

---

## 0. Контекст задачи

- Агент поддержки сотрудников по кадровым вопросам. Многоходовый чат.
- База знаний (БЗ): ~1600 инструкций в pgvector (эмбеддинги GigaChat). У инструкции есть `type`: `rag` (ответ текстом) или `api` (~100–150 шт., требуют вызовов внутренних API). **БЗ — бизнес-домен, техническая разметка в ней запрещена** (никаких тегов тулзов).
- 40 тулзов поверх ~20 внутренних API. Все тулзы **читающие**, мутирующих нет.
- Модель: GigaChat. Ограничения: **нет параллельных `tool_calls`**, structured output медленный (не используем), tool calling штатный работает нормально.
- SLA: **15 секунд на один HTTP-ответ**. Контракт с фронтом допускает ответ типа «прогресс»: бэк отдаёт текст, фронт перезванивает.
- Авторизация: есть эндпоинт, возвращающий группы пользователя. Внешние API права вызывающего не проверяют. Правила: «пользователь в группе G → может вызывать тулзу T по другим людям» и «пользователь — руководитель сотрудника → может вызывать тулзу по этому сотруднику» (есть API `manager_of(employee_id)`).
- Заявка: не мутация, а заполненный словарь полей + константы, который уходит на фронт. Поля заполняет модель из диалога; чего нет — спрашивает.
- Вспомогательные API: `find_course(filters)` — поиск курсов по подстроке названия, AND/OR фильтры, возвращает список курсов. Тулзы `find_employee` нет.

---

## 1. Ключевые решения (ADR, кратко)

| # | Решение | Отвергнуто |
|---|---|---|
| 1 | Один ReAct-агент на `create_agent` + middleware | Два контура, `turn_router`, направленный граф |
| 2 | Вопрос пользователю = завершение хода текстом без `tool_calls` | `interrupt()`, тулза `ask_user`, текстовые маркеры, structured output |
| 3 | Тулзы — чистые функции с явными параметрами; автор обращения — псевдоним `"me"`, резолвится внутри тулзы | Табельник в system prompt; `set_subject` в state; `whoami()` |
| 4 | Авторизация — middleware `wrap_tool_call` по таблице политик | Проверка моделью; проверка в каждой тулзе вручную |
| 5 | Связка «инструкция → тулза» через лексику описаний тулзов; при деградации на 40 тулзах — скиллы (фаза 2) | Разметка БЗ тулзами; `LLMToolSelectorMiddleware` (лишний вызов модели) |
| 6 | Заявка — тулза `create_ticket`, схема аргументов = форма; результат в state | Отдельный structured output |
| 7 | Контекст: `ContextEditingMiddleware` + `SummarizationMiddleware` с кастомным промптом | `tool_cache` / `render_known_facts` |
| 8 | SLA: фоновый запуск + очередь событий + бюджет 12 с на HTTP-ответ + тип «прогресс» | Сокращение шагов агента ради SLA |
| 9 | Бизнес-правила («уточни, по кому», «спроси курс») — в тексте инструкции; агент следует ей буквально | Дублирование бизнес-правил в промпте |

---

## 2. Компоненты

### 2.1 Контекст запуска (`context_schema`)

Собирается **до** запуска агента. В system prompt попадают только `today` и `role`. Табельный номер в тексте не появляется никогда.

```python
# hr_agent/context.py
from pydantic import BaseModel
from datetime import date

class RunContext(BaseModel):
    author_id: str          # табельный номер автора обращения
    groups: frozenset[str]  # из авторизационного эндпоинта
    role: str               # человекочитаемая роль для промпта (напр. "сотрудник", "HR-партнёр")
    today: date

async def build_context(user_id: str) -> RunContext:
    groups = await auth_api.get_groups(user_id)
    return RunContext(author_id=user_id, groups=frozenset(groups), role=derive_role(groups), today=date.today())
```

### 2.2 State

Кастомные поля объявляются через middleware (`state_schema`), т.к. `create_agent` расширяет state только так. `[ВЕРИФИЦИРОВАТЬ]`

```python
# hr_agent/state.py
from typing import NotRequired
from langchain.agents.middleware import AgentState, AgentMiddleware

class HRState(AgentState):
    ticket: NotRequired[dict | None]        # заполненная заявка (см. 2.4)
    active_skills: NotRequired[list[str]]   # фаза 2

class HRStateMiddleware(AgentMiddleware[HRState]):
    """Носитель схемы state. Хуков не реализует."""
    state_schema = HRState
```

### 2.3 Контракт тулзов

Общие правила для всех 40 API-тулзов и базовых:

1. **Явные параметры.** Никакого неявного субъекта. Тулза, работающая с сотрудником, принимает `employee_id: EmployeeRef` (или `list[EmployeeRef]`).
2. **Псевдоним автора.** `EmployeeRef` принимает либо табельный номер в строгом формате, либо литерал `"me"`. Резолв — внутри тулзы через `ToolRuntime.context`. Мусор → ошибка валидации, возвращаемая модели текстом.
3. **Результаты — сущности с ID и именем.** `{"id": 17, "name": "Школа скрам-мастеров"}`, а не голые числа. Модель ссылается на сущность, а не запоминает число.
4. **Валидация входных ID.** Тулза, принимающая ID, проверяет существование и возвращает понятную ошибку — испорченный моделью ID падает на первом вызове.
5. **Усечение.** Списки режутся до `MAX_ITEMS` с явным `"truncated": true`. Где возможно — фильтрующие параметры (период, статус), чтобы модель запрашивала узко.
6. **Ошибки — текстом, не исключением.** Тулза ловит ошибки API и возвращает `ToolError`-строку, понятную модели («Курс с ID 17 не найден»). Сетевые ошибки — на `ToolRetryMiddleware`.
7. **Описания тулзов — в лексике инструкций БЗ.** Это основной механизм маршрутизации после отказа от разметки БЗ. Описание должно содержать те же термины, которыми инструкции называют операцию («история обучения сотрудника», «причина назначения курса»).

```python
# hr_agent/tools/types.py
import re
from typing import Annotated
from pydantic import AfterValidator

EMPLOYEE_ID_RE = re.compile(r"^\d{6,8}$")   # [УТОЧНИТЬ формат]

def _validate_ref(v: str) -> str:
    if v == "me" or EMPLOYEE_ID_RE.fullmatch(v):
        return v
    raise ValueError(f'Ожидается табельный номер или "me", получено: {v!r}')

EmployeeRef = Annotated[str, AfterValidator(_validate_ref)]

def resolve(ref: str, ctx: "RunContext") -> str:
    return ctx.author_id if ref == "me" else ref
```

```python
# hr_agent/tools/api/training.py
from langchain.tools import tool, ToolRuntime

@tool
def get_training_history(
    employee_id: EmployeeRef,
    runtime: ToolRuntime[RunContext],
    period_from: date | None = None,
) -> dict:
    """История обучения сотрудника: пройденные курсы с датами и статусом.
    employee_id — табельный номер сотрудника или "me" (автор обращения)."""
    eid = resolve(employee_id, runtime.context)
    try:
        items = api.training_history(eid, period_from)
    except ApiNotFound:
        return tool_error(f"Сотрудник {eid} не найден")
    return truncated({"employee_id": eid, "courses": [c.model_dump() for c in items]}, key="courses")
```

### 2.4 Базовые тулзы (привязаны всегда)

| Тулза | Контракт |
|---|---|
| `search(query)` | Поиск по БЗ. Возвращает `candidates: [{id, title, type}]` (top-k, компактно) **и** `top_text` — полный текст первого кандидата, если отрыв по скору ≥ `GAP_THRESHOLD` `[УТОЧНИТЬ]`; иначе `top_text: null`. Экономит один вызов модели в типовом ходе. |
| `get_instruction(id)` | Полный текст инструкции `{id, title, type, text}`. Вызывается, когда кандидаты близки или нужна другая инструкция из списка. |
| `find_course(filters)` | Обёртка над существующим API. Возвращает `[{id, name}]`. Несколько совпадений — модель уточняет у пользователя. |
| `create_ticket(...)` | Схема аргументов = поля заявки. См. ниже. |

`create_ticket`: обязательные поля — обязательные аргументы. Нет поля → pydantic-ошибка → возвращается модели → модель спрашивает пользователя. Это структурный механизм «спроси недостающее» без промпт-правил.

```python
# hr_agent/tools/base.py
from langgraph.types import Command
from langchain_core.messages import ToolMessage

class TicketArgs(BaseModel):
    category: str = Field(description="Категория заявки из инструкции")
    employee_id: EmployeeRef
    description: str = Field(description="Суть обращения словами пользователя")
    # ... остальные поля формы [УТОЧНИТЬ список]

TICKET_CONSTANTS = {"source": "hr-agent", "channel": "chat"}   # [УТОЧНИТЬ]

@tool(args_schema=TicketArgs)
def create_ticket(runtime: ToolRuntime[RunContext], **args) -> Command:
    """Подготовить заявку в кадровую службу. Вызывать только после того, как инструкция
    предписывает создать заявку и все обязательные поля известны из диалога."""
    payload = {**args, "employee_id": resolve(args["employee_id"], runtime.context), **TICKET_CONSTANTS}
    return Command(update={
        "ticket": payload,
        "messages": [ToolMessage("Заявка подготовлена, сообщи пользователю её содержание", tool_call_id=runtime.tool_call_id)],
    })
```

### 2.5 API-тулзы и составные тулзы

- 40 тулзов группируются по доменам в `tools/api/<domain>.py` (курсы, отпуска, справки, …). Все следуют контракту 2.3.
- **Составные тулзы** (`tools/composite.py`): т.к. параллельных `tool_calls` нет, каждый хоп цепочки «получи ID → проверь по ID» стоит вызов модели. Для частых цепочек делаем одну тулзу, внутри которой ID не проходят через модель:

```python
@tool
def check_courses_in_history(employee_id: EmployeeRef, course_names: list[str], runtime: ToolRuntime[RunContext]) -> dict:
    """Проверить, есть ли в истории обучения сотрудника курсы с указанными названиями.
    Возвращает по каждому названию: найденные курсы и факт прохождения."""
    eid = resolve(employee_id, runtime.context)
    history_ids = {c.id for c in api.training_history(eid)}
    out = []
    for name in course_names:
        matches = api.find_course(name)
        out.append({"query": name, "courses": [{"id": c.id, "name": c.name, "completed": c.id in history_ids} for c in matches]})
    return {"employee_id": eid, "results": out}
```

Какие цепочки делать составными — определяется по eval (фаза 2), а не заранее. Составные тулзы — часть скилла, не БЗ.

### 2.6 Middleware

Порядок в списке важен: внешние оборачивают внутренние. `[ВЕРИФИЦИРОВАТЬ порядок применения wrap_* в установленной версии]`

```python
# hr_agent/agent.py
from langchain.agents import create_agent
from langchain.agents.middleware import (
    SummarizationMiddleware, ContextEditingMiddleware, ClearToolUsesEdit,
    ModelCallLimitMiddleware, ToolRetryMiddleware,
)

agent = create_agent(
    model=gigachat,
    tools=[search, get_instruction, find_course, create_ticket, *api_tools, *composite_tools],
    system_prompt=SYSTEM_PROMPT,           # см. 2.7; today/role подставляются динамически (см. ниже)
    context_schema=RunContext,
    middleware=[
        HRStateMiddleware(),
        DynamicPromptMiddleware(),          # wrap_model_call: подставляет today, role в system prompt
        AuthzMiddleware(POLICY),            # wrap_tool_call
        ProgressMiddleware(PROGRESS_TEXTS), # wrap_tool_call → stream writer
        ToolRetryMiddleware(max_retries=2, retry_on=(NetworkError,)),
        ContextEditingMiddleware(edits=[
            ClearToolUsesEdit(trigger=CTX_EDIT_TRIGGER, keep=6, exclude_tools=["get_instruction", "search"], clear_tool_inputs=False),
        ]),
        SummarizationMiddleware(model=gigachat, trigger=("tokens", SUMMARY_TRIGGER), keep=("messages", 40), summary_prompt=SUMMARY_PROMPT),
        ModelCallLimitMiddleware(run_limit=10, exit_behavior="end"),
    ],
    checkpointer=postgres_checkpointer,
)
```

Параметры `CTX_EDIT_TRIGGER`, `SUMMARY_TRIGGER` — в конфиг; калибруются по eval. `keep=40` сообщений ≈ 3–4 полных хода при 4–6 вызовах тулзов на ход.

**`clear_tool_inputs=False` — принципиально:** аргументы прошлых вызовов (`get_assignment(course_id=17)`) должны оставаться в контексте даже после очистки результатов — это то, что позволяет модели понять «а про другой курс?» как повтор шага с новым аргументом.

#### AuthzMiddleware

Таблица политик: тулза → правило. Субъекты извлекаются из аргументов **по типу параметра** (`EmployeeRef` / `list[EmployeeRef]` в `args_schema`), а не по имени — детерминированно.

```python
# hr_agent/policy.py
from dataclasses import dataclass

@dataclass(frozen=True)
class Rule:
    groups: frozenset[str] = frozenset()   # любая из групп даёт право на чужие данные
    manager_ok: bool = False               # руководитель субъекта имеет право

POLICY: dict[str, Rule] = {
    "get_training_history": Rule(groups=frozenset({"hr", "l&d"}), manager_ok=True),
    "get_hr_partner":       Rule(groups=frozenset(), manager_ok=False),   # только про себя
    # ... для всех 40 тулзов [ЗАПОЛНИТЬ]
}
DEFAULT_RULE = Rule()   # тулза без записи в POLICY — только "me"
```

```python
# hr_agent/middleware/authz.py
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

class AuthzMiddleware(AgentMiddleware):
    def __init__(self, policy: dict[str, Rule], manager_cache: TTLCache):
        self.policy, self.cache = policy, manager_cache

    def wrap_tool_call(self, request, handler):                 # [ВЕРИФИЦИРОВАТЬ сигнатуру]
        name = request.tool_call["name"]
        rule = self.policy.get(name, DEFAULT_RULE)
        ctx = request.runtime.context
        subjects = extract_employee_refs(request.tool, request.tool_call["args"])   # по типу EmployeeRef
        for s in subjects:
            if s == "me" or s == ctx.author_id:
                continue
            if rule.groups & ctx.groups:
                continue
            if rule.manager_ok and self._is_manager(ctx.author_id, s):
                continue
            return ToolMessage(
                content=f"Нет прав запрашивать эти данные по сотруднику {s}. Сообщи пользователю, что доступ ограничен.",
                tool_call_id=request.tool_call["id"], name=name, status="error",
            )
        return handler(request)

    def _is_manager(self, author: str, subject: str) -> bool:
        key = (author, subject)
        if key not in self.cache:
            self.cache[key] = api.manager_of(subject) == author
        return self.cache[key]
```

Требования: `extract_employee_refs` обходит `tool.args_schema` рекурсивно (поля типа `EmployeeRef`, `list[EmployeeRef]`, вложенные модели). Тулза без `EmployeeRef`-параметров проверку проходит без обращения к политике. Отказ логируется с `author_id`, `tool`, `subject`.

#### ProgressMiddleware

Шаблонные тексты, ноль вызовов модели. Пишутся в custom-stream, runtime отдаёт их фронту.

```python
# hr_agent/middleware/progress.py
from langgraph.config import get_stream_writer

PROGRESS_TEXTS = {
    "search": "Ищу подходящую инструкцию…",
    "get_instruction": "Читаю инструкцию…",
    "find_course": "Ищу курс по названию…",
    "create_ticket": "Готовлю заявку…",
}
DEFAULT_PROGRESS = "Запрашиваю данные…"

class ProgressMiddleware(AgentMiddleware):
    def wrap_tool_call(self, request, handler):
        get_stream_writer()({"progress": PROGRESS_TEXTS.get(request.tool_call["name"], DEFAULT_PROGRESS)})
        return handler(request)
```

#### DynamicPromptMiddleware

```python
class DynamicPromptMiddleware(AgentMiddleware):
    def wrap_model_call(self, request, handler):                # [ВЕРИФИЦИРОВАТЬ: request.override / system_prompt]
        ctx = request.runtime.context
        prompt = SYSTEM_PROMPT.format(today=ctx.today.isoformat(), role=ctx.role)
        return handler(request.override(system_prompt=prompt))
```

#### SkillsMiddleware — фаза 2, только при деградации на 40 тулзах

```python
# hr_agent/middleware/skills.py
SKILLS = {  # техническая шпаргалка + группа тулзов; живёт в коде, не в БЗ
    "training": Skill(tools=["get_training_history", "get_assignment", "check_courses_in_history"],
                      notes="Причина назначения берётся из get_assignment(course_id); course_id — из find_course."),
    # ...
}
BASE_TOOLS = {"search", "get_instruction", "find_course", "create_ticket", "activate_skill"}

@tool
def activate_skill(name: Literal[...]) -> Command:
    """Подключить набор инструментов для домена. Домены: training — обучение и курсы; ..."""
    return Command(update={"active_skills": [name], "messages": [ToolMessage(SKILLS[name].notes, ...)]})

class SkillsMiddleware(AgentMiddleware[HRState]):
    state_schema = HRState
    def wrap_model_call(self, request, handler):
        active = request.state.get("active_skills", [])
        allowed = BASE_TOOLS | {t for s in active for t in SKILLS[s].tools}
        return handler(request.override(tools=[t for t in request.tools if t.name in allowed]))
```

### 2.7 Промпты

**System prompt** — минимальный. Бизнес-правила не дублирует. Два суждения, которые остаются за моделью, сформулированы явно.

```
Ты — ассистент кадровой поддержки. Сегодня {today}. Роль пользователя: {role}.

Порядок работы:
1. По вопросу пользователя найди инструкцию (search). Если подходящих несколько и из диалога
   не понятно, какая нужна, — задай пользователю один уточняющий вопрос и заверши ответ.
2. Следуй найденной инструкции буквально, шаг за шагом. Если инструкция предписывает уточнить
   что-то у пользователя (например, по кому задан вопрос или какой курс имеется в виду) —
   задай вопрос и заверши ответ. Не додумывай ответ за пользователя.
3. Данные автора обращения запрашивай, передавая employee_id="me". Табельный номер другого
   сотрудника используй только если пользователь его назвал.
4. Если инструмент вернул ошибку доступа или «не найдено» — сообщи об этом пользователю честно.
5. Ответ пользователю — кратко, по существу инструкции. Если инструкция завершается созданием
   заявки — собери поля из диалога, недостающие спроси, затем вызови create_ticket и опиши
   пользователю, что в заявке.

Пользователь может задать несколько вопросов в одном сообщении или сменить тему — отвечай
на то, что спросили сейчас.
```

**Summary prompt** — обязан сохранить конкретные вещи, иначе теряется именно то, ради чего нужен контекст.

```
Сожми историю диалога в краткое резюме. Обязательно сохрани:
- активную инструкцию (id, название) и на каком её шаге остановились;
- все полученные факты ВМЕСТЕ с аргументами, для которых они получены
  (например: «причина назначения курса 17 „Школа скрам-мастеров“ сотруднику 123456 — …»,
  а не «причина назначения курса — …»);
- табельные номера других сотрудников, названные в диалоге, и кто они (руководитель, HR-партнёр, подчинённый);
- незакрытый вопрос ассистента к пользователю, если он был;
- заявки, которые были подготовлены.
Не сохраняй тексты инструкций целиком — только id и название.
```

### 2.8 Runtime (обёртка `BaseAgent`)

Граф про SLA не знает. Runtime:

- Запуск агента — фоновая `asyncio.Task`, читающая `agent.astream(input, config, context=ctx, stream_mode=["custom", "values"])`. Custom-события → `last_progress`; последний `values`-снапшот → финальный ответ (текст последнего `AIMessage`) и `state["ticket"]`.
- Реестр запусков по `thread_id`. Один активный запуск на тред; новое сообщение при активном запуске → `409 RUN_IN_PROGRESS` `[УТОЧНИТЬ с фронтом]`.
- HTTP ждёт `RESPONSE_BUDGET = 12s`. Не дождался → `ProgressResponse(last_progress)`. Фронт перезванивает с `continue=true`, обработчик подключается к той же задаче и снова ждёт бюджет.
- Жёсткий потолок на ход: `RUN_HARD_LIMIT = 90s` → отмена задачи, `FinalResponse("Не удалось завершить, попробуйте переформулировать")`, инцидент в лог.
- После финала запись реестра удаляется.

```python
# hr_agent/runtime/contracts.py
class AgentResponse(BaseModel):
    type: Literal["final", "progress"]
    text: str
    ticket: dict | None = None      # только при type="final", если заявка подготовлена

# hr_agent/runtime/runner.py
async def handle(thread_id: str, user_id: str, message: str | None, continue_: bool) -> AgentResponse:
    run = registry.get(thread_id)
    if run is None:
        if continue_ or message is None:
            raise NoActiveRun()
        ctx = await build_context(user_id)
        run = registry.start(thread_id, agent, HumanMessage(message), ctx)
    elif not continue_:
        raise RunInProgress()
    try:
        final = await asyncio.wait_for(asyncio.shield(run.final), timeout=RESPONSE_BUDGET)
    except asyncio.TimeoutError:
        return AgentResponse(type="progress", text=run.last_progress or DEFAULT_PROGRESS)
    registry.drop(thread_id)
    return AgentResponse(type="final", text=final.text, ticket=final.state.get("ticket"))
```

Чекпоинтер — Postgres (уже есть). Retention чекпоинтов: в саммари оседают табельники третьих лиц — срок хранения и доступ к таблице чекпоинтов согласовать до прода.

---

## 3. Сквозные сценарии (для проверки понимания)

**A. «Почему мне назначен курс?»**
1. `search("почему назначен курс")` → 1 кандидат с явным отрывом, `top_text` заполнен. Инструкция: «уточни, по себе или по другому сотруднику; спроси название курса; найди курс; получи причину назначения».
2. Модель: «По себе или по другому сотруднику? Какой курс?» → ход завершён (текст без `tool_calls`).
3. Пользователь: «По себе, „Школа скрам-мастеров“».
4. `find_course` → `[{id: 17, name: ...}]` → `get_assignment(employee_id="me", course_id=17)` → ответ.
5. Пользователь: «А про „Основы Agile“?» → в окне лежит инструкция и вызов `get_assignment(course_id=17)`; модель повторяет шаги 4 с новым курсом без нового `search`.

**B. Руководитель про подчинённого.**
1. Пользователь: «Прошёл ли мой сотрудник 234567 курсы „А“ и „Б“?»
2. `search` → инструкция типа `api`.
3. `check_courses_in_history(employee_id="234567", course_names=["А","Б"])` → `AuthzMiddleware`: автор не в HR-группе, `manager_ok=True`, `manager_of(234567) == author` → пропуск.
4. Ответ. Если бы автор не был руководителем — `ToolMessage` с отказом → модель сообщает об ограничении доступа.

**C. Заявка.**
1. Инструкция завершается «создай заявку категории X».
2. Модель вызывает `create_ticket(category="X", employee_id="me", description=...)`; поля `reason` нет → pydantic-ошибка → модель спрашивает `reason` → ход завершён.
3. Пользователь отвечает → `create_ticket` успешен → `state.ticket` заполнен → runtime отдаёт `FinalResponse(ticket=...)`.

---

## 4. Структура пакета

```
hr_agent/
  agent.py                 # сборка create_agent (2.6)
  context.py               # RunContext, build_context
  state.py                 # HRState, HRStateMiddleware
  policy.py                # POLICY, Rule, DEFAULT_RULE
  prompts.py               # SYSTEM_PROMPT, SUMMARY_PROMPT, PROGRESS_TEXTS
  config.py                # пороги: GAP_THRESHOLD, CTX_EDIT_TRIGGER, SUMMARY_TRIGGER, RESPONSE_BUDGET, RUN_HARD_LIMIT, MAX_ITEMS
  tools/
    types.py               # EmployeeRef, resolve, tool_error, truncated, extract_employee_refs
    base.py                # search, get_instruction, find_course, create_ticket
    api/<domain>.py        # 40 тулзов по доменам
    composite.py           # составные тулзы (фаза 2)
  middleware/
    authz.py
    progress.py
    dynamic_prompt.py
    skills.py              # фаза 2
  runtime/
    contracts.py           # AgentResponse
    runner.py              # registry, handle
  eval/
    dataset/               # см. раздел 5
    run_eval.py
tests/
```

---

## 5. Порядок работ

**Фаза 0 — измерения (до middleware).**
- Eval-набор: (а) 100–150 API-инструкций → ожидаемая последовательность вызовов тулзов и аргументов; (б) 30–50 RAG-кейсов; (в) кейсы: два вопроса в одном сообщении, смена темы посреди сценария, «а про другой курс?», отказ в доступе, неполная заявка.
- Замер: модель с полным набором из 40 тулзов на (а). Метрики: правильная тулза на первом шаге, правильная цепочка, порча ID. Результат решает, нужна ли фаза 2 (скиллы).
- Замер токенов: описания 40 тулзов + system prompt + типовой ход.

**Фаза 1 — ядро.** Всё из раздела 2, кроме `SkillsMiddleware` и `composite.py`. Порядок: типы и контракт тулзов → базовые тулзы → `AuthzMiddleware` + `POLICY` → сборка агента с context/summarization → runtime → прогон eval.

**Фаза 2 — по результатам eval.** Составные тулзы для цепочек, которые часто ломаются или не укладываются в SLA. `SkillsMiddleware` — только если фаза 0 показала деградацию на 40 тулзах.

---

## 6. Тесты (обязательные)

- `resolve` / `EmployeeRef`: `"me"`, валидный номер, мусор, номер из шаблона письма.
- `extract_employee_refs`: скаляр, список, вложенная модель, тулза без `EmployeeRef`.
- `AuthzMiddleware`: матрица {автор сам / группа есть / руководитель / чужой} × {правило с группой / с manager_ok / DEFAULT_RULE}; кэш `manager_of` вызывается один раз на пару.
- `search`: `top_text` заполняется только при отрыве ≥ порога.
- `create_ticket`: отсутствие обязательного поля → ошибка модели, а не исключение наружу; успех → `state.ticket`.
- Runtime: ответ «прогресс» при превышении бюджета; повторный вызов с `continue` подключается к той же задаче; `409` при новом сообщении во время запуска; жёсткий потолок отменяет задачу.
- Контекст: после `ClearToolUsesEdit` аргументы вызовов и тексты инструкций сохраняются; саммари (проверка на eval-диалогах) содержит факты с аргументами и активную инструкцию.
- Eval-харнесс: прогон датасета фазы 0 с отчётом по метрикам; запускается в CI по сокращённой выборке.

---

## 7. Анти-паттерны (не делать)

- `interrupt()`, HITL-middleware, тулза `ask_user`, текстовые маркеры типа `QUESTION:` — вопрос пользователю это конец хода.
- Табельный номер автора в system prompt или в шаблоне сообщения.
- Неявный «текущий субъект» в state (`set_subject`) — все субъекты только явными параметрами.
- Разметка БЗ техническими тегами — связка через описания тулзов и (при необходимости) скиллы в коде.
- Кэш результатов тулзов по `(tool, args)` — результаты зависят от аргументов и времени; история сообщений и есть память.
- `response_format` / structured output — заявка и «вопрос/ответ» решаются tool calling и завершением хода.
- Проверка прав моделью или внутри каждой тулзы вручную — только `AuthzMiddleware` + `POLICY`.
- `LLMToolSelectorMiddleware` — лишний вызов модели при SLA 15 с.

---

## 8. Открытые параметры `[УТОЧНИТЬ]`

- Формат табельного номера (regex).
- Полный список 40 тулзов с доменами и записями `POLICY`.
- Поля формы заявки и константы.
- `GAP_THRESHOLD` для `search`, `MAX_ITEMS` усечения.
- Протокол фронта: имя флага `continue`, поведение при новом сообщении во время запуска.
- Retention чекпоинтов и доступ к таблице.
- Имена авторизационных групп и правило вывода `role` из групп.
