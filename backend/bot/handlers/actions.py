"""
Обработчики действий с пользователями — S-Access Support

Все критические действия требуют подтверждения через inline кнопки.
"""
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


def _api_post(config, path, body=None):
    api_url = (config.get("remnawave_api_url") or "").rstrip("/")
    token = config.get("remnawave_api_token", "")
    if not api_url or not token:
        return False, "API не настроен"
    try:
        r = requests.post(
            f"{api_url}{path}",
            json=body or {},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        return r.status_code == 200, f"HTTP {r.status_code}" if r.status_code != 200 else "OK"
    except Exception as e:
        return False, str(e)


# ═══════════════════════════════════════════════════════════════════════════
#                    ПОДТВЕРЖДЕНИЯ (CONFIRM)
# ═══════════════════════════════════════════════════════════════════════════

def _confirm_keyboard(action: str, data: str):
    """Создаёт клавиатуру с кнопками Подтвердить/Отмена."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm:{action}:{data}"),
            InlineKeyboardButton("❌ Отмена", callback_data="cancel_action"),
        ]
    ])


# Описания действий для подтверждения
ACTION_DESCRIPTIONS = {
    "reset_traffic": ("🔄 Сброс трафика", "Вы уверены, что хотите сбросить трафик пользователя?"),
    "revoke_sub": ("🔑 Перевыпуск подписки", "Перевыпустить подписку? Будет сгенерирован новый ключ."),
    "enable": ("🔓 Разблокировка", "Разблокировать пользователя?"),
    "disable": ("🔒 Блокировка", "Заблокировать пользователя? Он потеряет доступ к VPN."),
    "hwid_del_all": ("🗑 Удаление всех HWID", "Удалить ВСЕ привязанные устройства пользователя?"),
}


async def show_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, uuid: str, username: str = ""):
    """Показывает окно подтверждения действия."""
    query = update.callback_query
    
    if action not in ACTION_DESCRIPTIONS:
        await query.answer("Неизвестное действие", show_alert=True)
        return
    
    title, description = ACTION_DESCRIPTIONS[action]
    user_info = f" для @{username}" if username else ""
    
    text = f"<b>{title}</b>{user_info}\n\n{description}"
    
    await query.edit_message_text(
        text=text,
        parse_mode="HTML",
        reply_markup=_confirm_keyboard(action, uuid)
    )


async def cancel_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена действия."""
    query = update.callback_query
    await query.answer("Действие отменено")
    await query.edit_message_text("❌ Действие отменено.", reply_markup=None)


async def confirm_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение и выполнение действия."""
    query = update.callback_query
    
    if not _check_access(query.from_user.id, context):
        await query.answer("Нет доступа.", show_alert=True)
        return
    
    data = query.data
    # confirm:action:uuid
    parts = data.split(":", 2)
    if len(parts) < 3:
        await query.answer("Ошибка данных", show_alert=True)
        return
    
    action = parts[1]
    uuid = parts[2]
    config = get_settings()
    
    result_text = ""
    ok = False
    
    if action == "reset_traffic":
        ok, msg = await asyncio.to_thread(_api_post, config, f"/api/users/{uuid}/actions/reset-traffic")
        result_text = "✅ Трафик успешно сброшен!" if ok else f"❌ Ошибка: {msg}"
    
    elif action == "revoke_sub":
        ok, msg = await asyncio.to_thread(_api_post, config, f"/api/users/{uuid}/actions/revoke")
        result_text = "✅ Подписка перевыпущена!" if ok else f"❌ Ошибка: {msg}"
    
    elif action == "enable":
        ok, msg = await asyncio.to_thread(_api_post, config, f"/api/users/{uuid}/actions/enable")
        result_text = "✅ Пользователь разблокирован!" if ok else f"❌ Ошибка: {msg}"
    
    elif action == "disable":
        ok, msg = await asyncio.to_thread(_api_post, config, f"/api/users/{uuid}/actions/disable")
        result_text = "✅ Пользователь заблокирован!" if ok else f"❌ Ошибка: {msg}"
    
    elif action == "hwid_del_all":
        try:
            user_id = int(uuid)
        except (TypeError, ValueError):
            result_text = "❌ Неверные данные"
        else:
            ok, msg = await asyncio.to_thread(_api_post, config, "/api/hwid/devices/delete-all", {"userId": user_id})
            result_text = "✅ Все устройства удалены!" if ok else f"❌ Ошибка: {msg}"
    
    elif action == "hwid_del":
        # hwid_del требует userId:hwid
        if ":" in uuid:
            real_id, hwid = uuid.split(":", 1)
            try:
                user_id = int(real_id)
            except (TypeError, ValueError):
                result_text = "❌ Неверные данные"
            else:
                ok, msg = await asyncio.to_thread(_api_post, config, "/api/hwid/devices/delete", {"userId": user_id, "hwid": hwid})
                result_text = "✅ Устройство удалено!" if ok else f"❌ Ошибка: {msg}"
        else:
            result_text = "❌ Неверные данные"
    
    else:
        result_text = "❌ Неизвестное действие"
    
    await query.answer()
    await query.edit_message_text(result_text, reply_markup=None)


# ═══════════════════════════════════════════════════════════════════════════
#                    ДЕЙСТВИЯ С ЗАПРОСОМ ПОДТВЕРЖДЕНИЯ
# ═══════════════════════════════════════════════════════════════════════════

async def action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка действий — теперь показывает подтверждение."""
    query = update.callback_query
    
    if not _check_access(query.from_user.id, context):
        await query.answer("Нет доступа.", show_alert=True)
        return
    
    data = query.data
    
    # Парсим действие и показываем подтверждение
    if data.startswith("act:reset_traffic:"):
        uuid = data.split(":", 2)[2]
        await show_confirmation(update, context, "reset_traffic", uuid)
    
    elif data.startswith("act:revoke_sub:"):
        uuid = data.split(":", 2)[2]
        await show_confirmation(update, context, "revoke_sub", uuid)
    
    elif data.startswith("act:enable:"):
        uuid = data.split(":", 2)[2]
        await show_confirmation(update, context, "enable", uuid)
    
    elif data.startswith("act:disable:"):
        uuid = data.split(":", 2)[2]
        await show_confirmation(update, context, "disable", uuid)
    
    elif data.startswith("act:hwid_del_all:"):
        uuid = data.split(":", 2)[2]
        await show_confirmation(update, context, "hwid_del_all", uuid)
    
    elif data.startswith("hwid_del:"):
        # hwid_del:uuid:hwid
        parts = data.split(":", 2)
        if len(parts) == 3:
            uuid, hwid = parts[1], parts[2]
            # Для удаления HWID передаём uuid:hwid
            await query.answer("Подтвердите удаление устройства", show_alert=False)
            text = f"<b>🗑 Удаление устройства</b>\n\nУдалить устройство?\n<code>{hwid[:20]}...</code>"
            await query.edit_message_text(
                text=text,
                parse_mode="HTML",
                reply_markup=_confirm_keyboard("hwid_del", f"{uuid}:{hwid}")
            )
