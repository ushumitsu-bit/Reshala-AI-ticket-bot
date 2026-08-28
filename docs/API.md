# 📚 Документация API TrueTunnel Support

## 🔗 Базовый URL
- **Локально:** `http://localhost:8001`
- **Продакшн:** `https://api.your-domain.com`

## 🔐 Авторизация
Все эндпоинты (кроме `/api/webhooks/*` и некоторых публичных) требуют авторизации Telegram Mini App через заголовок `Authorization` или `X-Telegram-Init-Data`, если не установлен `SKIP_AUTH=true` для разработки.

---

## 🎫 API Тикетов (`/api/tickets`)

### Получить активные тикеты
Возвращает список тикетов, требующих внимания менеджера (Эскалированные + Подозрительные).
- **GET** `/api/tickets/active`
- **Ответ:**
  ```json
  {
    "tickets": [
      {
        "id": "mongo_id",
        "client_id": 123456789,
        "status": "escalated",
        "reason": "AI не справился",
        "created_at": "2023-10-27T10:00:00"
      }
    ]
  }
  ```

### Получить эскалированные тикеты
Возвращает только тикеты, переданные менеджеру.
- **GET** `/api/tickets/escalated`

### Получить подозрительные тикеты
Возвращает только тикеты, отмеченные как подозрительные (пользователь не найден в системе).
- **GET** `/api/tickets/suspicious`

### Получить детали тикета
- **GET** `/api/tickets/{ticket_id}`

### Ответить на тикет
Отправить сообщение пользователю через бота от имени менеджера.
- **POST** `/api/tickets/{ticket_id}/reply`
- **Тело запроса:**
  ```json
  {
    "message": "Привет, мы всё починили!",
    "manager_name": "Александр"
  }
  ```

### Закрыть тикет
Пометить тикет как закрытый и архивировать топик.
- **POST** `/api/tickets/{ticket_id}/close`

### Удалить тикет
Убрать тикет из активного списка (скрыть/мягкое удаление).
- **POST** `/api/tickets/{ticket_id}/remove`

### Эскалировать тикет
Вручную эскалировать тикет на менеджера.
- **POST** `/api/tickets/{ticket_id}/escalate`
- **Тело запроса:**
  ```json
  { "reason": "Сложный вопрос" }
  ```

### Пометить как подозрительный
Вручную пометить тикет как подозрительный.
- **POST** `/api/tickets/{ticket_id}/mark-suspicious`

### Добавить вложение
Добавить файл или ссылку в контекст тикета (скриншот, ссылка и т.д.).
- **POST** `/api/tickets/{ticket_id}/add-attachment`
- **Тело запроса:**
  ```json
  { "type": "image", "value": "http://link.to/image.jpg" }
  ```

---

## 🤖 API Управления AI (`/api/ai`)

### Тест соединения с провайдером
Проверка валидности API ключа провайдера.
- **POST** `/api/ai/test-connection`
- **Тело запроса:**
  ```json
  { "provider": "openai", "key": "sk-..." }
  ```

### Получить доступные модели
Получить список моделей для конкретного провайдера.
- **GET** `/api/ai/models/{provider_name}`

### Установить активную модель
Выбрать, какую модель использовать для провайдера.
- **POST** `/api/ai/set-model`
- **Тело запроса:**
  ```json
  { "provider": "openai", "model": "gpt-4" }
  ```

### Установить активного провайдера
Выбрать, какой провайдер обрабатывает запросы пользователей.
- **POST** `/api/ai/set-active-provider`
- **Тело запроса:**
  ```json
  { "provider": "anthropic" }
  ```

### Тестовый чат
Отправить тестовое сообщение для проверки текущей конфигурации.
- **POST** `/api/ai/chat`
- **Тело запроса:**
  ```json
  { "message": "Как настроить VPN?", "provider": "openai" }
  ```

### Получить системный промпт
Получить текущий системный промпт с заполненными переменными.
- **GET** `/api/ai/stock-prompt`

---

## ⚡ API Действий (`/api/actions`)
*Взаимодействие с Remnawave Panel*

### Сбросить трафик
- **POST** `/api/actions/reset-traffic`
- **Тело запроса:** `{ "userUuid": "uuid-string" }`

### Перевыпустить подписку
Принудительно обновляет ключи подключения (Revoke).
- **POST** `/api/actions/revoke-subscription`
- **Тело запроса:** `{ "userUuid": "uuid-string" }`

### Включить/Отключить пользователя
- **POST** `/api/actions/enable-user`
- **POST** `/api/actions/disable-user`
- **Тело запроса:** `{ "userUuid": "uuid-string" }`

### Удалить HWID (Устройства)
Удалить конкретное или все устройства пользователя.
- **POST** `/api/actions/hwid-delete`
  - **Тело запроса:** `{ "userUuid": "...", "hwid": "..." }`
- **POST** `/api/actions/hwid-delete-all`
  - **Тело запроса:** `{ "userUuid": "..." }`

---

## 🔍 API Поиска (`/api/lookup`)

### Поиск пользователя
Поиск пользователя в Remnawave Panel по Telegram ID или Username.
- **POST** `/api/lookup`
- **Тело запроса:** `{ "query": "12345678" }` или `{ "query": "@username" }`
- **Ответ:** Возвращает объект пользователя, детали подписки и список HWID.

---

## 💰 API Bedolaga (`/api/bedolaga`)
*Интеграция с биллингом Bedolaga*

### Получить баланс
- **GET** `/api/bedolaga/balance/{telegram_id}`

### Получить историю пополнений
- **GET** `/api/bedolaga/deposits/{telegram_id}?limit=30`
