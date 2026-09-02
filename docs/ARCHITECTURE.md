# 🏗️ Архитектура Системы

## 📦 Обзор

S-Access Support — это модульная система, состоящая из нескольких Docker-контейнеров.

### Компоненты

1.  **Frontend (React Mini App)**
    - **Роль:** Панель управления (дашборд) менеджера внутри Telegram.
    - **Технологии:** React, Tailwind CSS, Lucide React.
    - **Работа:** Nginx раздает статические файлы билда.
    - **Порт:** Внутренний порт `3000`.

2.  **Backend (FastAPI)**
    - **Роль:** Ядро логики, API, работа с БД, обработка Telegram бота.
    - **Технологии:** Python, FastAPI, Motor (Async Mongo), python-telegram-bot.
    - **Порт:** Внутренний порт `8001`.
    - **Ключевые Сервисы:**
        - `TicketService`: Бизнес-логика тикетов.
        - `AIProviderManager`: Логика переключения AI провайдеров.
        - `Bot`: Polling обновлений Telegram.

3.  **База Данных (MongoDB)**
    - **Роль:** Постоянное хранилище данных.
    - **Коллекции:**
        - `tickets`: Активные тикеты поддержки.
        - `ticket_archive`: Закрытые тикеты (транскрипт для аналитики/самообучения, поле `distilled`).
        - `users`: Профили пользователей и контекст.
        - `settings`: Настройки системы.
        - `ai_providers`: API ключи и модели AI.
        - `knowledge_base`: Статьи базы знаний.
        - `kb_suggestions`: Черновики статей от AI для ревью менеджером.

4.  **Reverse Proxy (Nginx)**
    - **Роль:** Внешняя точка входа, SSL, маршрутизация.
    - **Конфигурация:** Проксирует `/api` на Backend, а `/` на Frontend.

## 🔄 Потоки Данных (Data Flow)

1.  **Сообщение Пользователя:**
    - Юзер пишет боту -> Бэкенд получает update.
    - Бэкенд проверяет, есть ли активный тикет.
    - **Если есть:** Сообщение добавляется в тикет.
    - **Если нет:** AI обрабатывает запрос (RAG по Базе Знаний) -> Генерирует ответ.
    - **Отказ AI/Эскалация:** Создается тикет со статусом `escalated`.

2.  **Действия Менеджера (Mini App):**
    - Менеджер открывает Mini App -> Загружается Frontend.
    - Frontend авторизуется через `Telegram WebApp Data`.
    - Frontend запрашивает тикеты (`escalated`) через API.
    - Менеджер отвечает -> Бэкенд шлет сообщение юзеру через Bot API.

3.  **Интеграции:**
    - **Remnawave:** Бэкенд запрашивает API Панели (статистика, подписка).
    - **Bedolaga:** Бэкенд запрашивает API Биллинга (баланс, транзакции).
    - **AI Providers:** Бэкенд ротирует ключи (OpenAI, Anthropic и т.д.) при ошибках.

## 🛠️ Docker Композиция

```yaml
services:
  mongodb:
    image: mongo:latest
    volumes:
      - mongodb_data:/data/db

  backend:
    build: ./backend
    depends_on:
      - mongodb
    env_file: .env

  frontend:
    build: ./frontend
    args:
      - REACT_APP_BACKEND_URL=${REACT_APP_BACKEND_URL}
    ports:
      - "3000:80"
```

## 🔒 Безопасность

- **Mini App Auth:** Middleware `verify_telegram_auth` проверяет подпись `initData` от Telegram ключом бота.
- **Защита API:** Rate limiting (лимиты запросов) на всех эндпоинтах.
- **Окружение:** Чувствительные данные (токены, mongo url) в `.env`.

## 📦 Закрытие и архив тикетов

- Все 3 пути закрытия (кнопка менеджера, API `/close`, клиентский колбэк) идут через единый `TicketService.close_ticket(ticket_ref, actor)`.
- При закрытии тикет **переносится в `ticket_archive`** (полный документ + `closed_at`, `closed_by`, `distilled: false`) и **удаляется из `tickets`**.
- Исключение: подозрительный тикет (`suspicious`), закрытый клиентом — остаётся в `tickets` со статусом `suspicious` и `closed_at` (для проверки менеджером).
- Архив хранит `history` для последующей дистилляции в базу знаний (Фаза 4).

## 🤖 Самообучение (KB Distiller)

- Фоновый воркер (`services/kb_distiller.py`, APScheduler) раз в `KB_DISTILL_INTERVAL_MIN` берёт из `ticket_archive` эскалированные тикеты с `distilled=false`.
- Фильтр «стоит ли учиться», скраббинг PII, поиск похожих статей, LLM-«методист» → черновик в `kb_suggestions` (`status=pending`).
- Менеджер подтверждает/правит/отклоняет через Mini App (`/api/kb-suggestions`). Автопубликации нет.
