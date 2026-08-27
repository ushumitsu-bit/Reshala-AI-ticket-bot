"""
Обработчик поиска пользователей — Решала support от DonMatteo
Ищет по Telegram ID, short UUID, username
"""
import re
import asyncio
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from utils.db_config import get_settings

logger = logging.getLogger(__name__)


def _check_access(user_id, context):
    config = get_settings()
    allowed = {str(x) for x in (config.get("allowed_manager_ids") or [])}
    return str(user_id) in allowed


def format_bytes(b):
    n = float(b or 0)
    for u in ['B', 'KB', 'MB', 'GB', 'TB']:
        if n < 1024:
            return f"{n:.2f} {u}"
        n /= 1024
    return f"{n:.2f} PB"


def _list_users(api_url, token):
    """Remnawave v3: GET /api/users (offset-pagination). Returns full user list."""
    headers = {"Authorization": f"Bearer {token}"}
    users = []
    start = 0
    size = 1000
    try:
        while True:
            r = requests.get(
                f"{api_url}/api/users",
                headers=headers,
                params={"start": start, "size": size},
                timeout=20,
            )
            if r.status_code != 200:
                break
            payload = r.json().get("response", {})
            batch = payload.get("users", []) if isinstance(payload, dict) else payload
            if not batch:
                break
            users.extend(batch)
            total = payload.get("total", 0) if isinstance(payload, dict) else len(users)
            if len(users) >= total or len(batch) < size:
                break
            start += size
    except Exception as e:
        logger.warning("list users: %s", e)
    return users


def _search_user(api_url, token, query):
    users = _list_users(api_url, token)
    q = query.strip().lstrip("@").lower()
    for u in users:
        tg = str(u.get("telegramId") or "").strip()
        short = (u.get("shortUuid") or "").strip().lower()
        vless = (u.get("vlessUuid") or "").strip().lower()
        username = (u.get("username") or "").strip().lower()
        description = (u.get("description") or "").lower()
        if (
            q == tg
            or q == short
            or q == vless
            or q == username
            or (q and f"@{q}" in description)
        ):
            return u
    return None


def _format_user_card(user):
    status = (user.get("status") or "UNKNOWN").upper()
    emoji = "✅" if status == "ACTIVE" else "❌" if status in ("DISABLED", "LIMITED", "EXPIRED") else "⏸"
    username_str = f"@{user['username']}" if user.get("username") else "Не указан"
    tg_id = user.get("telegramId", "N/A")
    uuid = user.get("vlessUuid") or user.get("uuid") or user.get("shortUuid") or "N/A"

    ut = user.get("userTraffic") or {}
    used = format_bytes(ut.get("usedTrafficBytes", 0)) if isinstance(ut, dict) and ut else "N/A"
    limit_bytes = user.get("trafficLimitBytes", 0)
    limit_str = format_bytes(limit_bytes) if limit_bytes and limit_bytes > 0 else "Безлимит"

    expire = user.get("expireAt", "N/A")
    if expire and expire != "N/A":
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(expire.replace("Z", "+00:00"))
            expire = dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            pass

    text = (
        f"{emoji} <b>Пользователь</b>\n\n"
        f"<b>UUID:</b> <code>{uuid}</code>\n"
        f"<b>Short:</b> <code>{user.get('shortUuid', 'N/A')}</code>\n"
        f"<b>Username:</b> {username_str}\n"
        f"<b>Telegram ID:</b> {tg_id}\n"
        f"<b>Статус:</b> {status}\n\n"
        f"<b>Трафик:</b> {used} / {limit_str}\n"
        f"<b>Истекает:</b> {expire}\n"
    )
    return text


def _user_actions_keyboard(user_id, status):
    user_id = str(user_id or "")
    is_disabled = (status or "").upper() == "DISABLED"
    buttons = [
        [
            InlineKeyboardButton("🔄 Сброс трафика", callback_data=f"act:reset_traffic:{user_id}"),
            InlineKeyboardButton("📋 Перевыпуск", callback_data=f"act:revoke_sub:{user_id}"),
        ],
        [
            InlineKeyboardButton("🗑 Все HWID", callback_data=f"act:hwid_del_all:{user_id}"),
        ],
    ]
    if is_disabled:
        buttons[1].append(InlineKeyboardButton("✅ Разблокировать", callback_data=f"act:enable:{user_id}"))
    else:
        buttons[1].append(InlineKeyboardButton("🚫 Заблокировать", callback_data=f"act:disable:{user_id}"))
    return InlineKeyboardMarkup(buttons)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений (поиск пользователей)."""
    user_id = update.effective_user.id
    if not _check_access(user_id, context):
        return False

    config = get_settings()
    query = (update.message.text or "").strip()
    if not query:
        return False

    uuid_pattern = re.compile(r'^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$', re.I)
    is_lookup = (
        query.isdigit()
        or query.startswith("@")
        or uuid_pattern.match(query)
        or (len(query) <= 20 and query.replace("-", "").isalnum())
    )
    if not is_lookup:
        return False

    api_url = (config.get("remnawave_api_url") or "").rstrip("/")
    api_token = config.get("remnawave_api_token", "")
    if not api_url or not api_token:
        await update.message.reply_text("API Remnawave не настроен. Используйте Mini App → Настройки.")
        return True

    msg = await update.message.reply_text("🔍 Ищу пользователя...")
    user = await asyncio.to_thread(_search_user, api_url, api_token, query)
    if not user:
        await msg.edit_text("Пользователь не найден.")
        return True

    text = _format_user_card(user)
    keyboard = _user_actions_keyboard(user.get("id", ""), user.get("status", ""))
    await msg.edit_text(text, parse_mode='HTML', reply_markup=keyboard)
    return True
