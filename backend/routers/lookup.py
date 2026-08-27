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
    user = None
    try:
        if query.isdigit():
            r = requests.get(f"{api_url}/api/users/by-telegram-id/{query}", headers=headers, timeout=10)
            if r.status_code == 200:
                data_resp = r.json()
                raw = data_resp.get("response")
                if isinstance(raw, list):
                    user = raw[0] if raw else None
                elif isinstance(raw, dict) and raw.get("uuid"):
                    user = raw
        else:
            username = query.lstrip("@")
            r = requests.get(f"{api_url}/api/users/by-username/{username}", headers=headers, timeout=10)
            if r.status_code == 200:
                user = r.json().get("response")
    except Exception as e:
        logger.warning(f"lookup error: {e}")
        return {"ok": False, "error": str(e)}

    if not user:
        return {"ok": False, "error": "user_not_found"}

    user_uuid = user.get("uuid")
    subscription = None
    hwid_devices = []

    if user_uuid:
        try:
            r = requests.get(f"{api_url}/api/subscriptions/by-uuid/{user_uuid}", headers=headers, timeout=10)
            if r.status_code == 200:
                subscription = r.json().get("response")
        except Exception:
            pass
        try:
            r = requests.get(f"{api_url}/api/hwid/devices/{user_uuid}", headers=headers, timeout=10)
            if r.status_code == 200:
                hwid_devices = r.json().get("response", {}).get("devices", [])
        except Exception:
            pass

    return {"ok": True, "user": user, "subscription": subscription, "hwid_devices": hwid_devices}
