# S-Access Support

AI-ассистент технической поддержки для VPN-сервиса на базе **Remnawave** и биллинга
**Bedolaga**. Бот принимает обращения клиентов в личке, отвечает через AI по базе знаний,
эскалирует сложное менеджеру и ведёт тикеты в группе поддержки. Управление — через
Telegram Mini App.

---

## Возможности

- **AI-автоответы.** 5 провайдеров (Groq, OpenAI, Anthropic, Google, OpenRouter) с
  автоматическим failover по ключам. AI отвечает по загруженной базе знаний, «мысли» в
  `<think>` вырезаются, при неуверенности — эскалация на менеджера.
- **Тикеты-топики.** Каждый клиент получает отдельный топик в группе поддержки. Статусы:
  открыт → эскалация → подозрительный → закрыт. Двусторонняя связь: ответ менеджера в
  топике уходит клиенту в личку бота.
- **Mini App для менеджеров.** Поиск пользователей в Remnawave (по Telegram ID / username /
  email), карточка клиента (UUID, трафик, подписка, HWID, баланс Bedolaga), действия
  (сброс трафика, перевыпуск подписки, блокировка, удаление HWID), работа с эскалированными
  тикетами, база знаний, настройки AI-провайдеров.
- **Самообучение (KB distiller).** Фоновый разбор архивных тикетов в черновики статей базы
  знаний с ревью менеджером.
- **Нативная тема.** Mini App подхватывает светлую/тёмную тему и акцентный цвет клиента
  Telegram.

Подробнее — [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/API.md`](docs/API.md).

---

## Архитектура

4 контейнера в одной Docker-сети:

| Контейнер | Роль | Порт |
|---|---|---|
| `reshala-mongodb` | MongoDB 7 (`--auth`) | внутренний |
| `reshala-backend` | FastAPI (Mini App API) | `8001` |
| `reshala-bot` | Telegram-бот (long polling) | — |
| `reshala-frontend` | React-статика за nginx | `80` (в контейнере) |

Frontend обращается к backend **напрямую из браузера** по `REACT_APP_BACKEND_URL`, поэтому
перед контейнерами нужен reverse-proxy (nginx/Caddy) с SSL. Настройки бота и секреты хранятся
в коллекции `settings` MongoDB; при первом старте она заполняется из `.env`.

---

## Быстрый старт (Docker Compose)

```bash
git clone https://github.com/ushumitsu-bit/Reshala-AI-ticket-bot.git
cd Reshala-AI-ticket-bot

cp .env.example .env
nano .env            # заполнить обязательные переменные (см. ниже)

docker compose up -d --build
docker compose ps    # должны быть healthy/running все 4 контейнера
```

Проверка backend:

```bash
curl -s http://localhost:8001/api/health
# {"status":"ok","service":"S-Access Support","database":"connected"}
```

---

## Переменные окружения

Полный список с пояснениями — [`docs/ENV.md`](docs/ENV.md). Минимум для запуска:

| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | токен бота от [@BotFather](https://t.me/BotFather) |
| `REMNAWAVE_API_URL` | базовый URL панели Remnawave (без `/api`) |
| `REMNAWAVE_API_TOKEN` | API-токен Remnawave (JWT) |
| `SUPPORT_GROUP_ID` | ID группы поддержки с топиками (начинается с `-100`) |
| `ALLOWED_MANAGER_IDS` | числовые Telegram ID менеджеров через запятую |
| `REACT_APP_BACKEND_URL` | публичный `https://` URL backend (виден браузеру) |
| `MINI_APP_DOMAIN` / `MINI_APP_URL` | публичный URL фронтенда (для кнопок бота) |
| `CORS_ORIGINS` | разрешённые Origin фронта через запятую, либо `*` |
| `SKIP_AUTH` | `false` в проде; `true` отключает проверку initData (только localhost) |
| `MONGO_INITDB_ROOT_USERNAME` / `MONGO_INITDB_ROOT_PASSWORD` | креды Mongo (**сменить пароль**) |
| `BEDOLAGA_API_URL` / `BEDOLAGA_API_TOKEN` | опционально, для баланса клиента |

> **`REACT_APP_BACKEND_URL` вшивается в бандл на этапе сборки**, а `CORS_ORIGINS` читается
> backend при старте. После их изменения:
> ```bash
> docker compose build --no-cache frontend   # если менялся REACT_APP_BACKEND_URL
> docker compose up -d                        # пересоздать контейнеры (не restart!)
> ```
> `docker compose restart` **не перечитывает** `.env`.

---

## Продакшн: reverse-proxy + SSL

В репозитории есть [`nginx.conf.example`](nginx.conf.example) — вариант с **одним доменом**
(`/api/` → backend, `/` → frontend, same-origin, CORS не нужен):

```bash
sudo apt update && sudo apt install -y nginx certbot python3-certbot-nginx
sudo cp nginx.conf.example /etc/nginx/sites-available/truetunnel
sudo nano /etc/nginx/sites-available/truetunnel        # заменить your-domain.com
sudo ln -s /etc/nginx/sites-available/truetunnel /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d your-domain.com
```

`.env` для одного домена:

```env
REACT_APP_BACKEND_URL=https://your-domain.com
MINI_APP_DOMAIN=https://your-domain.com
MINI_APP_URL=https://your-domain.com
CORS_ORIGINS=https://your-domain.com
```

**Вариант с двумя поддоменами** (`support.example.com` → frontend,
`api-support.example.com` → backend): два `server`-блока, и обязательно
`CORS_ORIGINS=https://support.example.com` — точное значение Origin фронта, со схемой,
без слэша в конце.

---

## Настройка бота

1. Создать бота у [@BotFather](https://t.me/BotFather), вставить токен в `BOT_TOKEN`.
2. **Menu Button в BotFather не задавать.** Кнопку Mini App бот ставит сам — персонально
   менеджеру после `/start`. У обычных пользователей её не будет.
3. Добавить бота в группу поддержки, включить топики, выдать право управлять темами. ID
   группы (`-100…`) → `SUPPORT_GROUP_ID`.
4. Узнать числовые Telegram ID менеджеров ([@userinfobot](https://t.me/userinfobot)) →
   `ALLOWED_MANAGER_IDS`.
5. Менеджер открывает бота, шлёт `/start` → появляется кнопка «Dashboard».

---

## Обновление

```bash
git pull --ff-only
docker compose build --no-cache
docker compose up -d
```

Если `git pull` жалуется на локальные правки `docker-compose.yml` (например, изменён порт
проброса фронта):

```bash
git stash
git pull --ff-only
git stash pop
```

---

## Траблшутинг

| Симптом | Причина / решение |
|---|---|
| Mini App: «Доступ запрещён», в логах backend `OPTIONS /api/... 400` | CORS preflight отклонён. `CORS_ORIGINS` не совпадает с Origin фронта или не применился. Проверить: `docker compose exec backend python -c "import os;print(os.environ.get('CORS_ORIGINS'))"`. Исправить `.env` → `docker compose up -d backend` (не restart). |
| `HTTP 403: Invalid initData signature` | `bot_token` в `db.settings` не совпадает с реальным токеном бота. Обновить в БД и `docker compose restart bot backend`. |
| `HTTP 403: Access denied: not a manager` | числовой Telegram ID менеджера не в `allowed_manager_ids`. Добавить в `.env` и в `db.settings`. |
| Поиск Remnawave: `status=403 Forbidden` | `remnawave_api_token` в `db.settings` перекрывает `.env`. Записать рабочий токен прямо в `db.settings`. |
| Кнопка Mini App видна обычным пользователям | В BotFather задан глобальный Menu Button URL — снять его. Бот при старте сбрасывает глобальную кнопку на «commands». |
| MongoDB: root-юзер не создаётся | На существующем volume `mongodb_data` root не пересоздаётся. Указать в `.env` те же креды, что уже в базе, либо создать пользователя в `mongosh`. |

---

## Структура проекта

```
Reshala-AI-ticket-bot/
├── backend/
│   ├── bot/            # Telegram-бот (handlers, keyboards)
│   ├── routers/        # FastAPI-эндпоинты Mini App
│   ├── services/       # AI, KB distiller, интеграции
│   ├── middleware/     # auth (валидация Telegram initData), rate limit
│   └── utils/          # конфиг из MongoDB + ENV
├── frontend/           # React Mini App (CRA)
├── docs/               # ARCHITECTURE / API / ENV / IMPROVEMENT_PLAN
├── nginx.conf.example  # пример host reverse-proxy
└── docker-compose.yml
```

---

## Вклад

PR и issue приветствуются — см. [`CONTRIBUTING.md`](CONTRIBUTING.md).
