import json
import urllib.parse

from slowapi import Limiter


def _get_request_key(request):
    """
    Ключ для rate limiting: user.id из initData (заголовок X-Telegram-Init-Data),
    фолбэк — X-Forwarded-For (nginx прокидывает реальный IP), затем прямой адрес.

    ВАЖНО: initData здесь НЕ проверяется по подписи — это НЕ security boundary.
    Ключ нужен лишь для изоляции бакетов между менеджерами.
    """
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    if init_data:
        try:
            parsed = urllib.parse.parse_qs(init_data)
            user_raw = parsed.get("user", [None])[0]
            if user_raw:
                user_id = json.loads(user_raw).get("id")
                if user_id is not None:
                    return f"user:{user_id}"
        except Exception:
            pass

    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()

    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=_get_request_key)
