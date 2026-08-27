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


def _search_user(api_url, token, query):
    headers = {"Authorization": f"Bearer {token}"}
    user = None
    if query.isdigit():
        try:
            r = requests.get(f"{api_url}/api/users/by-telegram-id/{query}", headers=headers, timeout=10)
            if r.status_code == 200:
                raw = r.json().get("response")
                if isinstance(raw, list):
                    user = raw[0] if raw else None
                elif isinstance(raw, dict) and raw.get("uuid"):
                    user = raw
        except Exception as e:
            logger.warning("search by tg id: %s", e)
    else:
        username = query.lstrip("@")
        try:
            r = requests.get(f"{api_url}/api/users/by-username/{username}", headers=headers, timeout=10)
            if r.status_code == 200:
                user = r.json().get("response")
        except Exception as e:
            logger.warning("search by username: %s", e)
    return user


def _format_user_card(user):
    status = (user.get("status") or "UNKNOWN").upper()
    emoji = "✅" if status == "ACTIVE" else "❌" if status == "DISABLED" else "⏸"
    username_str = f"@{user['username']}" if user.get("username") else "Не указан"
    tg_id = user.get("telegramId", "N/A")

    ut = user.get("userTraffic", {})
    used = format_bytes(ut.get("usedTrafficBytes", 0)) if ut else "N/A"
    limit_bytes = user.get("trafficLimitBytes", 0)
    limit_str = format_bytes(limit_bytes) if limit_bytes > 0 else "Безлимит"

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
        f"<b>UUID:</b> <code>{user.get('uuid', 'N/A')}</code>\n"
        f"<b>Short:</b> <code>{user.get('shortUuid', 'N/A')}</code>\n"
        f"<b>Username:</b> {username_str}\n"
        f"<b>Telegram ID:</b> {tg_id}\n"
        f"<b>Статус:</b> {status}\n\n"
        f"<b>Трафик:</b> {used} / {limit_str}\n"
        f"<b>Истекает:</b> {expire}\n"
    )
    return text


def _user_actions_keyboard(uuid, status):
    is_disabled = (status or "").upper() == "DISABLED"
    buttons = [
        [
            InlineKeyboardButton("🔄 Сброс трафика", callback_data=f"act:reset_traffic:{uuid}"),
            InlineKeyboardButton("📋 Перевыпуск", callback_data=f"act:revoke_sub:{uuid}"),
        ],
        [
            InlineKeyboardButton("🗑 Все HWID", callback_data=f"act:hwid_del_all:{uuid}"),
        ],
    ]
    if is_disabled:
        buttons[1].append(InlineKeyboardButton("✅ Разблокировать", callback_data=f"act:enable:{uuid}"))
    else:
        buttons[1].append(InlineKeyboardButton("🚫 Заблокировать", callback_data=f"act:disable:{uuid}"))
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
    keyboard = _user_actions_keyboard(user.get("uuid", ""), user.get("status", ""))
    await msg.edit_text(text, parse_mode='HTML', reply_markup=keyboard)
    return True
