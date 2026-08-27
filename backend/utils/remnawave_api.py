import httpx
import logging
from utils.db_config import get_settings

logger = logging.getLogger(__name__)

async def fetch_user_data(telegram_id: int) -> dict:
    """Получение полных данных пользователя из Remnawave v3 API"""
    config = get_settings()
    api_url = config.get("remnawave_api_url", "").rstrip("/")
    api_token = config.get("remnawave_api_token", "")

    if not api_url or not api_token:
        return {"not_configured": True}

    headers = {"Authorization": f"Bearer {api_token}"}
    result = {}

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            user = None
            start = 0
            size = 1000
            while user is None:
                r = await client.get(
                    f"{api_url}/api/users",
                    headers=headers,
                    params={"start": start, "size": size},
                )
                if r.status_code != 200:
                    break
                payload = r.json().get("response", {})
                batch = payload.get("users", []) if isinstance(payload, dict) else payload
                if not batch:
                    break
                for u in batch:
                    if str(u.get("telegramId") or "") == str(telegram_id):
                        user = u
                        break
                if user is not None:
                    break
                total = payload.get("total", 0) if isinstance(payload, dict) else len(batch)
                if len(batch) < size or start + size >= total:
                    break
                start += size

            if user is None:
                result["not_found"] = True
                return result

            result["user"] = user
            user_id = user.get("id")

            # HWID устройства (v3: GET /api/hwid/devices/{userId})
            if user_id is not None:
                try:
                    r2 = await client.get(f"{api_url}/api/hwid/devices/{user_id}", headers=headers)
                    if r2.status_code == 200:
                        dev = r2.json().get("response", {})
                        result["devices"] = dev.get("devices", []) if isinstance(dev, dict) else []
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"fetch_user_data: {e}")
        result["error"] = str(e)

    return result

async def remnawave_action(user_id, action_type: str) -> dict:
    """
    Выполнение действий над пользователем Remnawave v3.
    user_id — числовой id пользователя.
    action_type: reset_traffic, revoke_sub, disable, enable, hwid_all
    """
    config = get_settings()
    api_url = config.get("remnawave_api_url", "").rstrip("/")
    api_token = config.get("remnawave_api_token", "")

    if not api_url or not api_token:
        return {"error": "not_configured"}

    headers = {"Authorization": f"Bearer {api_token}"}

    try:
        async with httpx.AsyncClient(timeout=15) as http:
            if action_type == "reset_traffic":
                r = await http.post(f"{api_url}/api/users/{user_id}/actions/reset-traffic", headers=headers)
                return {"ok": r.status_code == 200, "status": r.status_code}

            elif action_type == "revoke_sub":
                r = await http.post(f"{api_url}/api/users/{user_id}/actions/revoke", json={}, headers=headers)
                return {"ok": r.status_code == 200, "status": r.status_code}

            elif action_type == "disable":
                r = await http.post(f"{api_url}/api/users/{user_id}/actions/disable", json={}, headers=headers)
                return {"ok": r.status_code == 200, "status": r.status_code}

            elif action_type == "enable":
                r = await http.post(f"{api_url}/api/users/{user_id}/actions/enable", json={}, headers=headers)
                return {"ok": r.status_code == 200, "status": r.status_code}

            elif action_type in ("hwid_all", "hwid_del_all"):
                r = await http.post(f"{api_url}/api/hwid/devices/delete-all", json={"userId": int(user_id)}, headers=headers)
                return {"ok": r.status_code == 200, "status": r.status_code}

    except Exception as e:
        logger.error(f"remnawave_action {action_type} error: {e}")
        return {"error": str(e)}

    return {"error": "unknown_action"}

