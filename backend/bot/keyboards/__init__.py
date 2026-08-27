from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def client_keyboard(is_suspicious=False):
    """Клавиатура для клиента (только базовые действия)"""
    buttons = [
        [
            InlineKeyboardButton("🔥 Вызвать менеджера", callback_data="ask_call_manager"),
            InlineKeyboardButton("✅ Закрыть тикет", callback_data="ask_close_ticket"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)

def confirm_client_keyboard(action: str):
    """Клавиатура подтверждения для клиентов."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Да", callback_data=action),
            InlineKeyboardButton("❌ Нет", callback_data="cancel_client_action"),
        ]
    ])

def build_support_keyboard(client_id, user_info=None, balance_data=None, is_suspicious=False, section="profile"):
    """Сложная клавиатура управления клиентом в топике поддержки."""
    rows = []
    
    # Навигация по секциям
    sections = [
        ("👤 Профиль", "profile"),
        ("📊 Трафик", "traffic"),
        ("📅 Даты", "dates"),
        ("🔗 Подписка", "subscription"),
        ("📱 Устройства", "hwid"),
        ("💰 Баланс", "balance"),
        ("📜 Транзакции", "transactions"),
    ]
    
    nav_row1 = []
    nav_row2 = []
    nav_row3 = []
    
    for i, (label, sec) in enumerate(sections):
        text = f"✓ {label}" if sec == section else label
        btn = InlineKeyboardButton(text, callback_data=f"sup:{client_id}:{sec}")
        if i < 3:
            nav_row1.append(btn)
        elif i < 5:
            nav_row2.append(btn)
        else:
            nav_row3.append(btn)
    
    if nav_row1: rows.append(nav_row1)
    if nav_row2: rows.append(nav_row2)
    if nav_row3: rows.append(nav_row3)
    
    # Действия если пользователь найден
    if user_info and user_info.get("id") is not None and not is_suspicious:
        status = user_info.get("status", "").upper()
        is_disabled = status in ("DISABLED", "INACTIVE", "BANNED")
        
        row_actions = [
            InlineKeyboardButton("🔄 Сброс трафика", callback_data=f"sup_act:{client_id}:reset_traffic"),
            InlineKeyboardButton("🔗 Перевыпуск", callback_data=f"sup_act:{client_id}:revoke_sub"),
        ]
        rows.append(row_actions)
        
        row_lock = []
        if is_disabled:
            row_lock.append(InlineKeyboardButton("🔓 Разблокировать", callback_data=f"sup_act:{client_id}:enable"))
        else:
            row_lock.append(InlineKeyboardButton("🔒 Заблокировать", callback_data=f"sup_act:{client_id}:disable"))
        
        row_lock.append(InlineKeyboardButton("🗑 Удалить HWID", callback_data=f"sup_act:{client_id}:hwid_all"))
        rows.append(row_lock)
    
    # Управление AI и тикетом
    rows.append([
        InlineKeyboardButton("🤖 Остановить AI", callback_data=f"sup_act:{client_id}:stop_ai"),
        InlineKeyboardButton("✅ Закрыть тикет", callback_data=f"close_ticket:{client_id}"),
    ])
    
    return InlineKeyboardMarkup(rows)
