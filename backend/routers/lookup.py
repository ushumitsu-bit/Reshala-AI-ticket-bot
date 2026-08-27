from fastapi import APIRouter, Body, Depends, Request
from typing import Optional
import requests
import os
import logging

from middleware.auth import require_manager
from middleware.rate_limit import limiter

router = APIRouter(dependencies=[Depends(require_manager)])
logger = logging.getLogger(__name__)


def _get_remnawave_config():
    from utils.db_config import get_settings
    settings = get_settings()
    if not settings:
        return None, None
    return (settings.get("remnawave_api_url") or "").rstrip("/"), settings.get("remnawave_api_token", "")


def format_bytes(b):
    n = float(b or 0)
    for u in ['B', 'KB', 'MB', 'GB', 'TB']:
        if n < 1024:
            return f"{n:.2f} {u}"
        n /= 1024
    return f"{n:.2f} PB"


def _list_users(api_url, headers):
    """Remnawave v3: GET /api/users (offset-pagination)."""
    users = []
    start = 0
    size = 1000
    try:
        while True:
            r = requests.get(f"{api_url}/api/users", headers=headers, params={"start": start, "size": size}, timeout=20)
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
        logger.warning(f"list users error: {e}")
    return users


def _find_user(users, query):
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


def _build_subscription(user):
    from datetime import datetime, timezone
    status = (user.get("status") or "").upper()
    ut = user.get("userTraffic") or {}
    expire = user.get("expireAt")
    days_left = None
    if expire:
        try:
            exp = datetime.fromisoformat(expire.replace("Z", "+00:00"))
            days_left = (exp - datetime.now(timezone.utc)).days
        except Exception:
            pass
    limit = user.get("trafficLimitBytes", 0)
    return {
        "isFound": True,
        "user": {
            "daysLeft": days_left,
            "trafficUsed": format_bytes(ut.get("usedTrafficBytes", 0)),
            "trafficLimit": format_bytes(limit) if limit and limit > 0 else "Безлимит",
            "isActive": status == "ACTIVE",
            "userStatus": status,
        },
    }


@router.post("")
@limiter.limit("30/minute")
def lookup_user(request: Request, data: dict = Body(...)):
    query = (data.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "query_required"}
    api_url, api_token = _get_remnawave_config()
    if not api_url or not api_token:
        return {"ok": False, "error": "remnawave_not_configured"}
    headers = {"Authorization": f"Bearer {api_token}"}

    try:
        users = _list_users(api_url, headers)
        user = _find_user(users, query)
    except Exception as e:
        logger.warning(f"lookup error: {e}")
        return {"ok": False, "error": str(e)}

    if not user:
        return {"ok": False, "error": "user_not_found"}

    # Совместимость с фронтом: v3 использует vlessUuid вместо uuid
    user.setdefault("uuid", user.get("vlessUuid") or user.get("shortUuid"))

    user_id = user.get("id")
    subscription = _build_subscription(user)
    hwid_devices = []

    if user_id is not None:
        try:
            r = requests.get(f"{api_url}/api/hwid/devices/{user_id}", headers=headers, timeout=10)
            if r.status_code == 200:
                resp = r.json().get("response", {})
                hwid_devices = resp.get("devices", []) if isinstance(resp, dict) else []
        except Exception:
            pass

    return {"ok": True, "user": user, "subscription": subscription, "hwid_devices": hwid_devices}
