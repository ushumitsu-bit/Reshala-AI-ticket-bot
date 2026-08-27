import html
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def esc(s):
    """Экранирование строки для Telegram HTML parse_mode."""
    if s is None:
        return ""
    return html.escape(str(s))


_ROLE_ALIASES = {"user": "client", "assistant": "ai"}


def normalize_role(role):
    """Приводит роль реплики к единому набору: client | ai | manager."""
    if not role:
        return "client"
    return _ROLE_ALIASES.get(role, role)


TOPIC_OPEN = "💬"
TOPIC_ESCALATED = "🔥"
TOPIC_SUSPICIOUS = "🚨"
TOPIC_CLOSED = "🟢"  # Используем 🟢 вместо ✅, так как Telegram удаляет ✅ из названий топиков

ESCALATION_TRIGGERS = [
    "уточнить у менеджера",
    "вызываю менеджера",
    "нужна помощь менеджера",
    "не могу ответить на этот вопрос",
    "передаю менеджеру",
    "require manager",
    "нужен менеджер",
    "обратитесь к менеджеру",
]

from utils.db_config import get_settings
import re

def check_access(user_id):
    config = get_settings()
    allowed = {str(x) for x in (config.get("allowed_manager_ids") or [])}
    return str(user_id) in allowed

def should_escalate(reply_text):
    if not reply_text:
        return True
    lower = reply_text.lower()
    return any(trigger in lower for trigger in ESCALATION_TRIGGERS)

def detect_subscription_link(text: str) -> str:
    """Попытка найти ссылку подписки в тексте"""
    patterns = [
        r'(https?://[^\s]+/sub/[^\s]+)',
        r'(https?://[^\s]+subscription[^\s]*)',
        r'(vless://[^\s]+)',
        r'(vmess://[^\s]+)',
        r'(trojan://[^\s]+)',
        r'(ss://[^\s]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def get_support_chat_ids(support_group_id):
    """
    Get list of support chat IDs (including migrated supergroup ID).
    """
    if support_group_id is None:
        return []
    ids = [support_group_id]
    if isinstance(support_group_id, int) and -10**9 <= support_group_id < 0 and support_group_id > -10**10:
        full_id = -(10**12 + abs(support_group_id))
        if full_id not in ids:
            ids.append(full_id)
    return ids

def format_bytes(b):
    """Форматирование байтов в читаемый вид"""
    n = float(b or 0)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if n < 1024:
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} PB"

def get_topic_name(username: str, status: str = "open") -> str:
    """
    Генерация стандартного имени топика.
    status: open, escalated, suspicious, closed
    """
    prefix = TOPIC_OPEN
    if status == "escalated":
        prefix = TOPIC_ESCALATED
    elif status == "suspicious":
        prefix = TOPIC_SUSPICIOUS
    elif status == "closed":
        prefix = TOPIC_CLOSED
        
    safe_username = str(username or "Unknown").strip().replace("@", "")
    return f"{prefix} @{safe_username}"[:128]


def build_support_header(user_info: dict, balance_data: dict, is_suspicious: bool, section: str = "profile") -> str:
    """
    Генерация HTML-заголовка для карточки тикета.
    Используется и в боте (при старте), и в API (при создании тикета).
    """
    user = user_info
    
    user_name = user.get("username") or user.get("first_name") or str(user.get("id", "Unknown"))
    telegram_id = user.get("telegramId") or user.get("id", "N/A")
    
    header_lines = [
        f"💬 <b>Тикет поддержки</b>",
        f"",
        f"👤 <b>Клиент:</b> @{user_name}",
        f"🆔 <b>Telegram ID:</b> <code>{telegram_id}</code>",
    ]
    
    # Баланс Bedolaga
    if balance_data and balance_data.get("balance") is not None:
        currency = balance_data.get("currency", "RUB")
        header_lines.append(f"💰 <b>Баланс:</b> {balance_data.get('balance', 0):.2f} {currency}")
    
    if is_suspicious:
        header_lines.append("")
        header_lines.append("⁉️ <b>Пользователь не найден в Remnawave!</b>")
        header_lines.append("<i>Проверьте данные вручную</i>")
        return "\n".join(header_lines)
    
    header_lines.append("")
    
    # Секция профиля (по умолчанию)
    if section == "profile" and user:
        header_lines.append("👤 <b>ПРОФИЛЬ</b>")
        header_lines.append("")
        header_lines.append(f"🆔 <b>UUID:</b> <code>{user.get('uuid', '—')}</code>")
        header_lines.append(f"📝 <b>Short UUID:</b> <code>{user.get('shortUuid', '—')}</code>")
        header_lines.append(f"🔢 <b>ID:</b> {user.get('id', '—')}")
        header_lines.append(f"👤 <b>Username:</b> @{user.get('username', '—')}")
        header_lines.append(f"📧 <b>Email:</b> {user.get('email') or 'Не указан'}")
        header_lines.append(f"💬 <b>Telegram ID:</b> {user.get('telegramId') or '—'}")
        header_lines.append(f"📊 <b>Статус:</b> {user.get('status', '—')}")
        header_lines.append(f"🏷️ <b>Тег:</b> {user.get('tag') or 'Не указан'}")
        if user.get('hwidDeviceLimit'):
            header_lines.append(f"📱 <b>Лимит устройств:</b> {user.get('hwidDeviceLimit')}")

    # Секция трафика
    elif section == "traffic" and user:
        header_lines.append("📊 <b>ТРАФИК</b>")
        header_lines.append("")
        traffic = user.get("userTraffic", {})
        if traffic:
            used = traffic.get("usedTrafficBytes", 0)
            lifetime = traffic.get("lifetimeUsedTrafficBytes", 0)
            limit = user.get("trafficLimitBytes", 0)
            header_lines.append(f"📥 <b>Использовано:</b> {format_bytes(used)}")
            header_lines.append(f"📈 <b>Всего использовано:</b> {format_bytes(lifetime)}")
            header_lines.append(f"📊 <b>Лимит:</b> {format_bytes(limit) if limit > 0 else 'Безлимит'}")
            header_lines.append(f"🔄 <b>Стратегия сброса:</b> {user.get('trafficLimitStrategy', 'NO_RESET')}")
            if traffic.get("onlineAt"):
                header_lines.append(f"🟢 <b>Онлайн:</b> {traffic.get('onlineAt')[:19].replace('T', ' ')}")
        else:
            header_lines.append("Нет данных о трафике.")

    # Секция даты
    elif section == "dates" and user:
        header_lines.append("📅 <b>ДАТЫ</b>")
        header_lines.append("")
        expire = user.get("expireAt")
        if expire:
            try:
                exp_date = datetime.fromisoformat(expire.replace('Z', '+00:00'))
                days_left = (exp_date - datetime.now(timezone.utc)).days
                emoji = "✅" if days_left > 0 else "❌"
                header_lines.append(f"⏰ <b>Истекает:</b> {exp_date.strftime('%d.%m.%Y %H:%M')} ({days_left} дн.) {emoji}")
            except:
                header_lines.append(f"⏰ <b>Истекает:</b> {expire[:19]}")
        created = user.get("createdAt")
        if created:
            header_lines.append(f"📅 <b>Создан:</b> {created[:19].replace('T', ' ')}")
        updated = user.get("updatedAt")
        if updated:
            header_lines.append(f"🔄 <b>Обновлен:</b> {updated[:19].replace('T', ' ')}")

    # Секция подписка
    elif section == "subscription" and user:
        header_lines.append("🔗 <b>ПОДПИСКА</b>")
        header_lines.append("")
        expire = user.get("expireAt")
        if expire:
            try:
                exp_date = datetime.fromisoformat(expire.replace('Z', '+00:00'))
                days_left = (exp_date - datetime.now(timezone.utc)).days
                header_lines.append(f"📊 <b>Дней осталось:</b> {days_left}")
            except:
                pass
        traffic = user.get("userTraffic", {})
        if traffic:
            used = traffic.get("usedTrafficBytes", 0)
            limit = user.get("trafficLimitBytes", 0)
            header_lines.append(f"📥 <b>Использовано:</b> {format_bytes(used)}")
            header_lines.append(f"📊 <b>Лимит:</b> {format_bytes(limit) if limit > 0 else 'Безлимит'}")
        status = user.get("status", "—")
        is_active = status.upper() in ("ACTIVE", "ENABLED")
        header_lines.append(f"✅ <b>Активна:</b> {'Да' if is_active else 'Нет'}")
        header_lines.append(f"📊 <b>Статус:</b> {status}")

    # Секция HWID
    # Секция HWID
    elif section == "hwid":
        header_lines.append("📱 <b>ПРИВЯЗАННЫЕ УСТРОЙСТВА (HWID)</b>")
        header_lines.append("")
        header_lines.append("<i>Нажмите кнопку ниже для просмотра/удаления устройств</i>")
    
    # Секция Баланс (Bedolaga)
    elif section == "balance":
        header_lines.append("💰 <b>БАЛАНС (BEDOLAGA)</b>")
        header_lines.append("")
        if balance_data:
             currency = balance_data.get("currency", "RUB")
             bal = balance_data.get("balance", 0)
             header_lines.append(f"💰 <b>Текущий баланс:</b> {bal} {currency}")
             
             # Example deposit info if available
             # deposits = balance_data.get("deposits", [])
        else:
             header_lines.append("Баланс: Нет данных")

    # Секция Транзакции
    elif section == "transactions":
        header_lines.append("📜 <b>ТРАНЗАКЦИИ (BEDOLAGA)</b>")
        header_lines.append("")
        
        txs = balance_data.get("transactions", [])
        if txs:
            for t in txs[:10]:
                amount = t.get("amount_rubles") or (t.get("amount_kopeks", 0) / 100)
                typ = t.get("type") or "—"
                desc = (t.get("description") or "—")[:40]
                created = (t.get("created_at") or "—")[:16].replace("T", " ")
                header_lines.append(f"<small>{created}</small> <b>{amount}₽</b> {typ}")
                header_lines.append(f"  <i>{desc}</i>")
        else:
             header_lines.append("Нет последних транзакций.")

    return "\n".join(header_lines)

def format_user_context(user_data: dict, balance_data: dict = None, has_provided_proof: bool = False, main_bot_username: str = "") -> str:
    """
    Форматирование контекста для AI.
    """
    # Пользователь не найден — специальный скрытый контекст
    if user_data.get("not_found"):
        if has_provided_proof:
            bot_mention = f"@{main_bot_username}" if main_bot_username else "основной бот"
            return f"""## СТАТУС: ПОЛЬЗОВАТЕЛЬ НЕ НАЙДЕН В СИСТЕМЕ

Пользователь прислал скриншот или ссылку подписки, но его НЕТ в нашей базе данных.

ТВОЙ ОТВЕТ ДОЛЖЕН БЫТЬ ТАКИМ:
"К сожалению, я проверил вашу информацию и не нашёл активной подписки в нашей системе.

Возможно, подписка была оформлена на другой аккаунт или истекла.

Для оформления новой подписки, пожалуйста, перейдите в {bot_mention}

Если вы уверены, что подписка была оформлена — нажмите кнопку 'Вызвать менеджера' и мы разберёмся в ситуации."

ВАЖНО: Будь вежлив, не обвиняй в мошенничестве."""
        else:
            return """## ВНУТРЕННЯЯ ИНФОРМАЦИЯ (НЕ ГОВОРИ ПОЛЬЗОВАТЕЛЮ!)
У меня нет данных об этом пользователе в системе. Но я НЕ должен говорить ему об этом напрямую!

СТРАТЕГИЯ:
1. Веди себя как обычный техподдержка
2. Для диагностики запроси скриншот главного экрана VPN-приложения
3. Или попроси прислать ссылку подписки (обычно начинается с https:// или vless://)
4. Скажи что это нужно для диагностики проблемы
5. НЕ ГОВОРИ что пользователя нет в системе!

ПРИМЕРЫ ФРАЗ:
- "Для диагностики проблемы пришлите, пожалуйста, скриншот главного экрана вашего VPN-приложения"
- "Можете прислать ссылку вашей подписки? Это поможет мне проверить настройки"
- "Покажите скриншот — так я смогу быстрее понять в чём дело"

После получения скриншота или ссылки — система определит следующий шаг."""

    if user_data.get("not_configured"):
        return "## API Remnawave не настроен. Данные пользователя недоступны."

    user = user_data.get("user")
    if not user:
        return "## Данные пользователя не найдены."
    
    devices = user_data.get("devices", [])
    traffic = user.get("userTraffic", {})
    
    parts = [
        "## ДАННЫЕ ТЕКУЩЕГО ПОЛЬЗОВАТЕЛЯ:",
        f"- Username: @{user.get('username', 'не указан')}",
        f"- Telegram ID: {user.get('telegramId', 'N/A')}",
        f"- UUID: {user.get('uuid', 'N/A')}",
        f"- Статус подписки: {user.get('status', 'UNKNOWN')}",
    ]
    
    expire_at = user.get("expireAt")
    if expire_at:
        try:
            exp_date = datetime.fromisoformat(expire_at.replace('Z', '+00:00'))
            days_left = (exp_date - datetime.now(timezone.utc)).days
            status_emoji = "✅" if days_left > 0 else "❌"
            parts.append(f"- Истекает: {exp_date.strftime('%d.%m.%Y')} ({days_left} дней) {status_emoji}")
        except:
            parts.append(f"- Истекает: {expire_at}")
    
    if traffic:
        used = traffic.get("usedTrafficBytes", 0)
        limit = user.get("trafficLimitBytes", 0)
        parts.append(f"- Использовано трафика: {format_bytes(used)}")
        parts.append(f"- Лимит трафика: {format_bytes(limit) if limit > 0 else 'Безлимит'}")
    
    hwid_limit = user.get("hwidDeviceLimit", 0)
    parts.append(f"- Устройств подключено: {len(devices)} из {hwid_limit}")
    
    if balance_data and balance_data.get("balance") is not None:
        parts.append(f"- Баланс (Bedolaga): {balance_data.get('balance', 0)} {balance_data.get('currency', 'RUB')}")
        
    return "\n".join(parts)
