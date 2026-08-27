# План доработок — Reshala AI ticket bot

Документ для агента-исполнителя. Составлен по результатам код-ревью + запрос на «самообучение по диалогам».

---

## 0. Как пользоваться этим документом

- Работать **по фазам сверху вниз**. Фаза 3 — обязательный пререквизит фазы 4.
- Каждая задача: `Проблема → Файлы → Что сделать → Критерии приёмки`.
- После выполнения задачи ставить `[x]` и дописывать строку в раздел **Журнал** внизу.
- Один PR = одна фаза (или одна задача, если фаза большая). Ветка от `main`.
- Не коммитить и не пушить без явного запроса пользователя.
- Сообщения об ошибках/строки для пользователя — **на русском** (проект русскоязычный).

## 1. Контекст архитектуры (не сломать)

- `bot` и `backend` — **разные процессы/контейнеры**, общаются только через MongoDB. Нельзя рассчитывать на общую память.
- `bot` — `python-telegram-bot`, long polling, **async event loop**. Блокирующие вызовы (`requests`, тяжёлый CPU) в хендлерах недопустимы.
- `backend` — FastAPI. Синхронные `def`-эндпоинты уходят в threadpool, поэтому `requests` там терпим, но не в bot.
- Персистентность бота — `PicklePersistence` в `/data/bot_state.pickle`. В `bot_data` **не класть секреты** (см. фазу 0).
- Настройки: слой `utils/db_config.get_settings()` мержит ENV → Mongo `settings` (одна запись).
- Тестов у backend нет. В рамках плана завести `backend/tests/` (pytest, уже в requirements).

## 2. Ручные шаги для пользователя (агент выполнить не может)

- [ ] Отозвать текущий `BOT_TOKEN` у @BotFather и выпустить новый.
- [ ] Перевыпустить `REMNAWAVE_API_TOKEN` в панели.
- [ ] После фазы 0 — почистить историю git от `bot_data/bot_state.pickle` (`git filter-repo` / BFG). Агент готовит инструкцию, выполняет пользователь.
- [ ] Закрыть порт `8001` от внешнего мира на хосте (firewall), оставить доступ только через nginx.

---

## Фаза 0 — Утечка секретов (блокер, делать первой)

### 0.1 [x] Убрать pickle-состояние из репозитория
- **Проблема:** `bot_data/bot_state.pickle` закоммичен и содержит живой `bot_token`, Remnawave JWT, `support_group_id`, `allowed_manager_ids`, переписку клиентов.
- **Файлы:** `.gitignore`, `bot_data/`, `docker-compose.yml`.
- **Что сделать:**
  - `git rm --cached bot_data/bot_state.pickle`.
  - В `.gitignore` добавить `bot_data/` и `*.pickle`.
  - Проверить, что volume-маунт `./bot_data:/data` в `docker-compose.yml` сохраняется (файл должен жить на хосте, не в git).
  - Создать `bot_data/.gitkeep`.
  - Подготовить в этом файле (раздел «Журнал») команду для истории git и передать пользователю.
- **Критерии приёмки:** `git ls-files | grep pickle` пусто; бот стартует и создаёт pickle локально.

### 0.2 [x] Не сохранять секреты в `bot_data`
- **Проблема:** `backend/bot/main.py` кладёт весь `_config` (с токенами) в `application.bot_data["_config"]`, который пишется в pickle.
- **Файлы:** `backend/bot/main.py`, `backend/bot/handlers/*` (используют `context.application.bot_data["_config"]`).
- **Что сделать:**
  - Не хранить `_config` в `bot_data`. Вместо этого — модуль-синглтон с TTL-кэшем настроек (см. задачу 2.5) в `utils/db_config.py`, из которого читают и хендлеры, и `post_init`.
  - `bot/handlers/search.py` и `bot/handlers/actions.py` перевести с `_get_config(context)` на общий `get_settings()`.
- **Критерии приёмки:** в свежем `bot_state.pickle` нет полей `bot_token` / `*_token`; хендлеры работают.

---

## Фаза 1 — Безопасность API

### 1.1 [x] Серверная проверка «пользователь — менеджер»
- **Проблема:** `verify_telegram_auth` проверяет только подпись `initData`, не сверяет `user.id` с `allowed_manager_ids`. Любой, открывший Mini App, имеет валидный `initData`.
- **Файлы:** `backend/middleware/auth.py`, все роутеры в `backend/routers/`.
- **Что сделать:**
  - Добавить зависимость `require_manager` в `middleware/auth.py`: вызывает `verify_telegram_auth`, затем проверяет `user["id"] in get_settings()["allowed_manager_ids"]`, иначе `403`.
  - В dev-режиме (`SKIP_AUTH=true`) поведение сохранить (dummy-менеджер).
- **Критерии приёмки:** запрос к защищённому эндпоинту с валидным `initData` не-менеджера → `403`.

### 1.2 [x] Навесить аутентификацию на открытые роутеры
- **Проблема:** без `Depends` вообще: `routers/actions.py`, `routers/lookup.py`, `routers/knowledge.py`, `routers/bedolaga.py`, а также `routers/settings.py` — `get_providers` / `update_provider` / `add_provider_key` / `remove_provider_key`.
- **Файлы:** перечисленные роутеры + `backend/server.py`.
- **Что сделать:**
  - `actions`, `lookup`, `bedolaga`, `settings` (все ручки), `ai` — `APIRouter(dependencies=[Depends(require_manager)])`.
  - `knowledge` — GET можно `require_manager`, write-ручки тоже `require_manager` (позже фаза 4 добавит сюда же suggestions).
  - Проверить, что фронт (`frontend/src`) шлёт `X-Telegram-Init-Data` во все эти вызовы (сейчас часть — да, проверить `pages/*`).
- **Критерии приёмки:** каждый `/api/*` (кроме `/api/health`) отвечает `401/403` без валидного менеджерского `initData`. Прогнать `curl` по списку.

### 1.3 [x] Ограничить `update_provider`
- **Проблема:** `routers/settings.py:update_provider` принимает любые поля, включая `base_url`, `endpoint`, `proxy` → SSRF / эксфильтрация API-ключей на чужой хост.
- **Файлы:** `backend/routers/settings.py`.
- **Что сделать:**
  - Белый список изменяемых полей: `enabled`, `selected_model`, `vision_model`, `display_name`, `models`.
  - `base_url` / `endpoint` / `proxy` — либо запретить через API совсем, либо валидировать по allowlist доменов и логировать изменение.
- **Критерии приёмки:** попытка записать `endpoint` через API игнорируется/отклоняется.

### 1.4 [x] initData: проверка свежести
- **Проблема:** `verify_telegram_auth` не проверяет `auth_date` — перехваченный `initData` валиден вечно (replay).
- **Файлы:** `backend/middleware/auth.py`.
- **Что сделать:** отклонять, если `now - auth_date > TELEGRAM_INITDATA_TTL` (env, дефолт 24 ч).
- **Критерии приёмки:** старый `initData` (подделать `auth_date`) → `403`.

### 1.5 [x] CORS
- **Проблема:** `allow_origins=["*"]` + `allow_credentials=True` в `backend/server.py`.
- **Что сделать:** `allow_origins` из env `CORS_ORIGINS` (список доменов Mini App), `allow_credentials=False` (auth идёт заголовком, не куками).
- **Критерии приёмки:** запрос с постороннего Origin не проходит preflight.

### 1.6 [x] Rate limiting за прокси
- **Проблема:** `slowapi` c `get_remote_address` за nginx видит один IP → лимит общий на всех. Открытые роутеры без лимита вообще.
- **Файлы:** `backend/middleware/rate_limit.py`, `nginx.conf.example`, роутеры.
- **Что сделать:**
  - `key_func`: брать `user.id` из провалидированного `initData`, фолбэк — `X-Forwarded-For` (nginx уже прокидывает).
  - Навесить `@limiter.limit` на `actions` (строже: 10/min), `lookup`, `bedolaga`, `knowledge` write.
- **Критерии приёмки:** превышение лимита одним пользователем не блокирует другого.

---

## Фаза 2 — Надёжность

### 2.1 [x] Убрать блокирующие вызовы из event loop бота
- **Проблема:** `ai_manager.chat()` (sync `requests`, таймауты 30–60 c, при failover ×N ключей) вызывается прямо в async-хендлере `support_client.py:get_ai_reply`. Также `requests` в `bot/handlers/search.py`, `bot/handlers/actions.py`.
- **Файлы:** `backend/bot/handlers/support_client.py`, `search.py`, `actions.py`.
- **Что сделать:** оборачивать в `await asyncio.to_thread(...)`. (Полный переход `AIProviderManager` на `httpx.AsyncClient` — опционально, отдельной задачей, не в этом плане.)
- **Критерии приёмки:** во время запроса к AI бот отвечает `/start` другому пользователю без задержки (ручная проверка / лог таймингов).

### 2.2 [x] Экранировать regex в поиске по базе знаний
- **Проблема:** `support_client.py:~98` и `routers/ai_router.py:~247` — слова из сообщения клиента идут в Mongo `$regex` без `re.escape` → regex-инъекция / ReDoS.
- **Файлы:** `backend/bot/handlers/support_client.py`, `backend/routers/ai_router.py`.
- **Что сделать:** `re.escape` каждое слово; ограничить кол-во слов (уже есть лимиты), отсечь слишком длинные токены.
- **Критерии приёмки:** сообщение `(a+)+$ aaaaaaaaaaaaaaa!` не роняет и не вешает запрос; юнит-тест на билд запроса.

### 2.3 [x] Экранировать пользовательский текст в Telegram HTML
- **Проблема:** текст клиента/имя вставляются в `parse_mode="HTML"` (`f"👤 @{user_name}:\n{text}"` и др.). Символ `<` → `BadRequest: can't parse entities` → **сообщение клиента молча не доходит** до менеджеров.
- **Файлы:** `backend/bot/handlers/support_client.py` (`forward_media_to_support`, ответы), `support_manager.py`, `services/telegram_service.py`, `services/ticket_service.py`.
- **Что сделать:** ввести хелпер `esc(s) = html.escape(s)` и применять ко всем интерполяциям пользовательских данных; либо для чисто пользовательского контента слать без `parse_mode`.
- **Критерии приёмки:** сообщение с `<`, `&`, `>` доставляется в топик и клиенту без ошибок.

### 2.4 [x] Гонка при создании топика/тикета
- **Проблема:** два быстрых сообщения клиента → обе ветки не находят тикет → два `create_forum_topic` + два документа.
- **Файлы:** `backend/bot/handlers/support_client.py`, `backend/database/indexes.py`.
- **Что сделать:**
  - Партиальный уникальный индекс: `client_id` при `status != closed & is_removed != true` (partial filter expression).
  - На создании — `insert_one` в try/except `DuplicateKeyError`, при конфликте перечитать существующий тикет.
  - Опционально: `asyncio.Lock` per `user_id` в памяти процесса как быстрый барьер.
- **Критерии приёмки:** скрипт, шлющий 5 сообщений подряд, создаёт **один** топик и один тикет.

### 2.5 [x] Кэш настроек
- **Проблема:** `get_settings()` дёргается на каждое сообщение/несколько раз за апдейт; при наличии ENV-значений делает `update_one(upsert=True)` каждый раз.
- **Файлы:** `backend/utils/db_config.py`.
- **Что сделать:**
  - TTL-кэш (например 30–60 c) на результат `get_settings()`.
  - Синхронизацию ENV→Mongo делать один раз при старте (или при промахе кэша), не на каждый вызов.
  - Функция `invalidate_settings_cache()` — вызывать после `PUT /api/settings` и тоглов в боте.
- **Критерии приёмки:** N последовательных `get_settings()` = 1 запрос к Mongo; изменение через Mini App видно боту в пределах TTL.

### 2.6 [x] Ленивое подключение к БД в роутерах
- **Проблема:** `routers/settings.py`, `knowledge.py`, `ai_router.py` делают `db = get_db()` на уровне модуля — падение при импорте, если Mongo ещё не поднялась.
- **Что сделать:** перевести на зависимость `get_database` из `dependencies.py` или на вызов `get_db()` внутри ручек.
- **Критерии приёмки:** backend стартует при недоступной Mongo и отдаёт осмысленную 500 на запросах, не крешится.

### 2.7 [x] Мелкий фикс `_call_openai_compat`
- **Проблема:** 5xx от провайдера → `return None` без исключения → `chat()` не считает это сбоем ключа, не ротирует.
- **Файлы:** `backend/services/ai/manager.py`.
- **Что сделать:** на `>=500` и таймауте — `raise`, чтобы сработал перебор ключей/провайдеров.

---

## Фаза 3 — Консолидация закрытия тикетов (пререквизит фазы 4)

### 3.1 [x] Единый путь закрытия
- **Проблема:** закрытие в трёх местах с разной логикой: `TicketService.close_ticket`, `support_client.client_close_ticket_callback`, кнопка `close_ticket:` в `support_manager`.
- **Файлы:** `backend/services/ticket_service.py`, `backend/bot/handlers/support_client.py`, `backend/bot/handlers/support_manager.py`, `backend/routers/tickets.py`.
- **Что сделать:** всё закрытие проводить через `TicketService.close_ticket(ticket_ref, actor: "manager"|"client", actor_id)`. Хендлеры бота создают `TicketService` (как уже делает `close_ticket_callback`) и вызывают его. Убрать дублирующий код и прямые `db.tickets.delete_one` из хендлеров.
- **Критерии приёмки:** все 3 UI-пути закрытия дают одинаковый результат в БД/Telegram.

### 3.2 [x] Архив вместо хард-делита
- **Проблема:** `close_ticket` и клиентский колбэк делают `delete_one` — теряется транскрипт (нужен для аналитики и фазы 4).
- **Файлы:** `backend/services/ticket_service.py`, `backend/database/indexes.py`.
- **Что сделать:**
  - Коллекция `ticket_archive`: полный документ тикета + `closed_at`, `closed_by`, `distilled: false`.
  - `close_ticket`: переносить в архив, затем удалять из `tickets` (или `status: closed` + TTL-индекс на 30 дней в `tickets`, а архив вечный — выбрать один подход, описать в `docs/ARCHITECTURE.md`).
  - Индексы архива: `distilled`, `closed_at`, `client_id`.
- **Критерии приёмки:** после закрытия тикет исчезает из активных списков, но его `history` доступна в `ticket_archive`.

### 3.3 [x] Нормализовать роли в `history`
- **Проблема:** клиент пишется как `role: "user"`, AI как `"ai"` (в памяти — `"assistant"`), менеджер — `"manager"`. Медиа-сообщения в `history` не попадают (только текст).
- **Файлы:** `backend/bot/handlers/support_client.py`, `support_manager.py`, `backend/services/ticket_service.py`.
- **Что сделать:** единый набор `client | ai | manager` + хелпер `append_history(ticket_id, role, content, meta)`. Для медиа писать плейсхолдер (`[photo]` и т.п.).
- **Критерии приёмки:** в новом тикете все реплики в `history` с консистентными ролями.

### 3.4 [x] Прочие баги закрытия
- `client_close_ticket_callback`: `thread_id` может быть `None` → `delete_one({"topic_id": None})`. Защититься проверкой.
- Менеджер, пишущий боту в ЛС не-lookup текст, попадает в `handle_client_message` и заводит тикет на себя (`dispatch_message`). Добавить: если `check_access(user_id)` и это не lookup — не создавать клиентский тикет, ответить подсказкой.

---

## Фаза 4 — Самообучение по диалогам (MVP)

Цель: после закрытия эскалированного тикета сформировать **черновик** статьи базы знаний и отдать менеджеру на подтверждение. **Без автопубликации в живую базу.**

### 4.1 [x] Схема данных
- **Файлы:** `backend/database/indexes.py`, `docs/ARCHITECTURE.md`.
- **Что сделать:**
  - `knowledge_base` — новые поля: `source: "manual"|"auto"`, `origin_ticket_id`, `question_patterns: [str]`, `usage_count: 0`, `last_used_at`, `tags: [str]`.
  - Коллекция `kb_suggestions`: `{_id, transcript: [...], summary, proposed: {title, category, tags, question_patterns, content}, similar: [{article_id, score}], action: "add"|"update", target_article_id?, status: "pending"|"approved"|"rejected"|"edited", created_at, reviewed_by, reviewed_at, source_ticket_id}`.
  - Индексы: `kb_suggestions.status`, `kb_suggestions.created_at`.

### 4.2 [x] Фоновый воркер дистилляции
- **Где:** в `backend` (не в боте). Планировщик — APScheduler (добавить в requirements) внутри FastAPI `lifespan`, интервал из env `KB_DISTILL_INTERVAL_MIN` (дефолт 15).
- **Файлы:** новый `backend/services/kb_distiller.py`, `backend/server.py` (регистрация job), `backend/services/ai/manager.py` (переиспользовать).
- **Алгоритм:**
  1. Взять из `ticket_archive` до K документов с `distilled == false`.
  2. **Фильтр «стоит ли учиться»:** был `status == "escalated"` на момент закрытия, менеджер отправил ≥1 реплику, в `history` ≥4 содержательных сообщения, не `suspicious`. Иначе — пометить `distilled: true, distill_result: "skipped_filter"` и дальше.
  3. **Скраббинг PII:** удалить/замаскировать TG ID, email, UUID, `vless://|vmess://|trojan://|ss://|https://…/sub/…` ссылки, номера — из транскрипта перед отправкой в LLM.
  4. **Похожие статьи:** текущим текстовым поиском (`$regex` по ключевым словам summary, с `re.escape`) достать топ-3 статьи.
  5. **LLM-«методист»** (отдельный промпт, не клиентский): вход — очищенный транскрипт + 3 похожие статьи; выход строго JSON:
     `{should_add: bool, action: "add"|"update", target_article_id: str|null, title, category, tags: [..], question_patterns: [..], content, reasoning}`.
     Промпт требует: не включать данные конкретного пользователя; если ответ менеджера выглядит неверным/небезопасным → `should_add: false`; если тема уже покрыта похожей статьёй → `action: "update"` или `should_add: false`.
  6. Если `should_add` → создать `kb_suggestions` со `status: "pending"`. Иначе — залогировать причину.
  7. Пометить архивный тикет `distilled: true` + `distill_result`.
- **Критерии приёмки:** закрыли тестовый эскалированный тикет с ответом менеджера → в течение интервала появился `kb_suggestions.pending` с осмысленным черновиком; PII в `proposed.content` отсутствует.

### 4.3 [x] API для ревью черновиков
- **Файлы:** новый `backend/routers/kb_suggestions.py`, `backend/server.py`.
- **Ручки (все `require_manager`):**
  - `GET /api/kb-suggestions?status=pending` — список.
  - `GET /api/kb-suggestions/{id}` — деталь с транскриптом и похожими статьями.
  - `POST /api/kb-suggestions/{id}/approve` — тело может содержать отредактированные поля; создаёт/обновляет `knowledge_base` (`source: "auto"`, `origin_ticket_id`), ставит `status: "approved"|"edited"`.
  - `POST /api/kb-suggestions/{id}/reject` — `status: "rejected"`, опционально `reason`.
- **Критерии приёмки:** approve создаёт статью в `knowledge_base`, она начинает участвовать в RAG бота; reject не создаёт ничего.

### 4.4 [x] UI в Mini App
- **Файлы:** `frontend/src/pages/` — новая `KnowledgeSuggestionsPage.js` (или вкладка в `KnowledgePage.js`), `frontend/src/components/Navigation.js`, `App.js`.
- **Что сделать:** список черновиков с бейджем количества `pending`; экран деталей — транскрипт, похожие статьи, редактируемые поля черновика, кнопки «Добавить в базу» / «Отклонить».
- **Критерии приёмки:** менеджер может принять/поправить/отклонить черновик из Mini App.

### 4.5 [x] Уведомление менеджеров
- При появлении `pending`-черновика — сообщение в группу поддержки (в «General» топик или отдельный) со ссылкой на Mini App. Env-флаг `KB_SUGGESTION_NOTIFY` (дефолт on).

---

## Фаза 5 — Самообучение V2 (после обкатки MVP)

- **5.1 Эмбеддинги для новизны/дедупа.** Хранить `embedding` у статей и у `kb_suggestions.summary`. Порог: `<0.80` — новая тема (add), `0.80–0.92` — update существующей, `>0.92` — skip. Провайдер эмбеддингов — через тот же `AIProviderManager` (OpenAI `text-embedding-3-small` / совместимый) или локальная модель; хранилище — Mongo Atlas Vector Search либо ручной косинус.
- **5.2 Гейт по повторам.** Коллекция `pending_patterns {summary, embedding, count, first_seen}`. Промотировать в `kb_suggestions` только когда `count >= KB_MIN_OCCURRENCES` (дефолт 2–3), чтобы разовые случаи не засоряли базу.
- **5.3 Векторный RAG в боте.** Заменить `$regex`-поиск по `knowledge_base` на векторный (то же хранилище, что 5.1).
- **5.4 Джоба консолидации.** Периодически находить near-duplicate статьи (`score > 0.95`) и предлагать менеджеру слияние (`kb_suggestions` c `action: "merge"`).
- **5.5 Метрики качества.** Трекать: доля тикетов, где AI ответил по `source: "auto"` статье и тикет **не** эскалировался; кнопка 👎 у менеджера на статью (`knowledge_base.downvotes`); дашборд в Mini App.

---

## Фаза 6 — Чистка (можно параллельно, низкий приоритет)

- [x] `bot/handlers/settings.py` — либо зарегистрировать (`CommandHandler("settings")`, `CallbackQueryHandler(pattern="^cfg:")`, MessageHandler для `awaiting_key_for`), либо удалить файл и импорты в `main.py`. Решить с пользователем: нужен ли конфиг AI из бота, если всё есть в Mini App. **По умолчанию — удалить.**
- [x] Удалить пустую заглушку `rename_topic` в `support_manager.py`.
- [x] Удалить неиспользуемый `manager_keyboard`; no-op `squad_assign_callback`, `button_callback`, `support_card_callback` — убрать вместе с регистрацией паттернов, если фичи не планируются.
- [x] `docker-compose.yml` — убрать устаревший `version: '3.8'`.
- [x] Хардкод `EMERGENT_LLM_KEY = "sk-emergent-..."` в `services/ai/manager.py` — убрать дефолт, читать только из env; если Emergent не используется — вырезать ветку целиком.
- [x] README (systemd-вариант): `ExecStart` backend должен запускать `uvicorn server:app`, а не `python3 server.py` (нет `__main__`). Либо добавить `__main__` с `uvicorn.run`.
- [x] MongoDB: включить аутентификацию (`MONGO_INITDB_ROOT_*`, `--auth`, `MONGO_URL` с кредами).

---

## Тестирование

Завести `backend/tests/` (pytest + pytest-asyncio уже в requirements). Минимум:

- `test_auth.py` — подпись initData валидна/невалидна, `auth_date` протух, не-менеджер → 403.
- `test_routers_authz.py` — параметризованный проход по всем `/api/*`: без `initData` → 401/403.
- `test_kb_query.py` — билд Mongo-запроса из зловредного сообщения не содержит некорректный regex.
- `test_telegram_escape.py` — форматирование сообщений с `<&>`.
- `test_ticket_close.py` — 3 пути закрытия → идентичный результат; архивирование.
- `test_kb_distiller.py` — фильтр «стоит ли учиться»; скраббинг PII; парсинг JSON от LLM (LLM замокать).

Ручная проверка бота: два параллельных диалога во время запроса к AI; спам 5 сообщений → один тикет; сообщение с HTML-спецсимволами доходит.

---

## Порядок и зависимости

```
Фаза 0  ──►  Фаза 1  ──►  Фаза 2
                              │
                              ▼
                          Фаза 3  ──►  Фаза 4  ──►  Фаза 5
Фаза 6 — в любой момент, отдельными мелкими PR.
```

---

## Журнал

| Дата | Фаза/задача | Что сделано | PR/commit |
|------|-------------|-------------|-----------|
| 2026-08-27 | Фаза 0.1 | `git rm --cached bot_data/bot_state.pickle`; в `.gitignore` добавлены `bot_data/` и `*.pickle`; создан `bot_data/.gitkeep`; volume `./bot_data:/data` в docker-compose оставлен; локальный pickle удалён | не коммитил (по правилу) |
| 2026-08-27 | Фаза 0.2 (+ часть 2.5) | Убрано сохранение `_config` в `bot_data` (main.py); введён TTL-кэш `get_settings()` + `invalidate_settings_cache()` в `utils/db_config.py`; `search.py`/`actions.py` переведены на `get_settings()`; тоглы в боте и `PUT /api/settings` сбрасывают кэш | не коммитил (по правилу) |

| 2026-08-27 | Фаза 1 | `require_manager` в `middleware/auth.py`; авторизация навешана на `actions`/`lookup`/`bedolaga`/`knowledge`/`settings`/`ai`/`tickets`; whitelist полей в `update_provider`; проверка свежести `initData` (TTL); CORS из env; rate limit по `user.id` из initData; фронт шлёт `X-Telegram-Init-Data` во все вызовы | не коммитил (по правилу) |

| 2026-08-27 | Фаза 2 (+тесты) | Блокирующие вызовы (`ai_manager.chat`, `_search_user`, `_api_post`, `test_connection`) в `asyncio.to_thread`; экранирование regex в БЗ (`support_client`, `ai_router`); хелпер `esc()` + экранирование HTML в `support_manager`/`ticket_service`/`support_client`; partial unique index на `client_id` + обработка `DuplicateKeyError`; ленивое подключение БД в `settings`/`knowledge`/`ai_router`/`actions`/`lookup`; фикс `_call_openai_compat` (5xx/timeout → raise). Заведены `backend/tests/` (18 тестов, зелёные) | не коммитил (по правилу) |

| 2026-08-27 | Фаза 3 | Единый `TicketService.close_ticket(ticket_ref, actor)` для 3 путей; архив в `ticket_archive` (индексы `distilled`/`closed_at`/`client_id`) вместо `delete_one`; хелпер `append_history` + `normalize_role` (client|ai|manager) и медиа-плейсхолдеры; guard `thread_id=None`; менеджер с не-lookup текстом больше не создаёт тикет на себя | не коммитил (по правилу) |

| 2026-08-27 | Фаза 4 | `kb_suggestions` + поля `knowledge_base` (source/origin_ticket_id/question_patterns/usage_count/tags) + индексы; воркер `services/kb_distiller.py` (APScheduler в lifespan, фильтр/скраббинг PII/похожие/LLM-методист); роутер `/api/kb-suggestions` (list/get/approve/reject); Mini App `KnowledgeSuggestionsPage` + бейдж в навигации; уведомление в группу (`KB_SUGGESTION_NOTIFY`) | не коммитил (по правилу) |

| 2026-08-27 | Фаза 6 | Удалён `bot/handlers/settings.py` (не был зарегистрирован); удалены `rename_topic`, `manager_keyboard`, no-op `squad_assign_callback`/`button_callback`/`support_card_callback` (+ регистрации); убран `version: '3.8'`; убран хардкод `EMERGENT_LLM_KEY`; README systemd → `uvicorn server:app`; MongoDB auth (`MONGO_INITDB_ROOT_*`, `--auth`, `MONGO_URL` с кредами) | не коммитил (по правилу) |

### Инструкция для пользователя: чистка git-истории от `bot_data/bot_state.pickle`

Файл удалён из текущего дерева, но его **история** осталась в git (живые токены/переписки). Выполнить после отзыва `BOT_TOKEN` и `REMNAWAVE_API_TOKEN`:

```bash
# 1. Установить git-filter-repo (один раз)
pip install git-filter-repo

# 2. Удалить файл из всей истории
git filter-repo --invert-paths --path bot_data/bot_state.pickle --force

# 3. Переподключить remote (filter-repo его отцепляет) и запушить
git remote add origin <URL_РЕПОЗИТОРИЯ>
git push origin --force --all
git push origin --force --tags
```

Все, кто клонировал репозиторий, должны переклонировать его заново (`git clone`), а не тянуть `pull`.
