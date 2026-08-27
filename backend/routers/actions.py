from fastapi import APIRouter, Body, Depends, Request
import requests
import os
import logging

from middleware.auth import require_manager
from middleware.rate_limit import limiter

router = APIRouter(dependencies=[Depends(require_manager)])
logger = logging.getLogger(__name__)


def _get_api():
    from utils.db_config import get_settings
    settings = get_settings()
    if not settings:
        return None, None
    return (settings.get("remnawave_api_url") or "").rstrip("/"), settings.get("remnawave_api_token", "")


def _api_post(path: str, body=None):
    api_url, token = _get_api()
    if not api_url or not token:
        return False, "API not configured"
    try:
        r = requests.post(
            f"{api_url}{path}",
            json=body or {},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15
        )
        return r.status_code == 200, f"HTTP {r.status_code}" if r.status_code != 200 else "OK"
    except Exception as e:
        return False, str(e)


@router.post("/reset-traffic")
@limiter.limit("10/minute")
def reset_traffic(request: Request, data: dict = Body(...)):
    uuid = str(data.get("userUuid", "")).strip()
    if not uuid:
        return {"ok": False, "error": "userUuid required"}
    ok, msg = _api_post(f"/api/users/{uuid}/actions/reset-traffic")
    return {"ok": ok, "message": "Трафик сброшен." if ok else msg}


@router.post("/revoke-subscription")
@limiter.limit("10/minute")
def revoke_sub(request: Request, data: dict = Body(...)):
    uuid = str(data.get("userUuid", "")).strip()
    if not uuid:
        return {"ok": False, "error": "userUuid required"}
    ok, msg = _api_post(f"/api/users/{uuid}/actions/revoke")
    return {"ok": ok, "message": "Подписка перевыпущена." if ok else msg}


@router.post("/enable-user")
@limiter.limit("10/minute")
def enable_user(request: Request, data: dict = Body(...)):
    uuid = str(data.get("userUuid", "")).strip()
    if not uuid:
        return {"ok": False, "error": "userUuid required"}
    ok, msg = _api_post(f"/api/users/{uuid}/actions/enable")
    return {"ok": ok, "message": "Профиль включён." if ok else msg}


@router.post("/disable-user")
@limiter.limit("10/minute")
def disable_user(request: Request, data: dict = Body(...)):
    uuid = str(data.get("userUuid", "")).strip()
    if not uuid:
        return {"ok": False, "error": "userUuid required"}
    ok, msg = _api_post(f"/api/users/{uuid}/actions/disable")
    return {"ok": ok, "message": "Профиль заблокирован." if ok else msg}


@router.post("/hwid-delete-all")
@limiter.limit("10/minute")
def hwid_delete_all(request: Request, data: dict = Body(...)):
    uuid = str(data.get("userUuid", "")).strip()
    if not uuid:
        return {"ok": False, "error": "userUuid required"}
    try:
        user_id = int(uuid)
    except (TypeError, ValueError):
        return {"ok": False, "error": "invalid userUuid"}
    ok, msg = _api_post("/api/hwid/devices/delete-all", {"userId": user_id})
    return {"ok": ok, "message": "Все устройства удалены." if ok else msg}


@router.post("/hwid-delete")
@limiter.limit("10/minute")
def hwid_delete(request: Request, data: dict = Body(...)):
    uuid = str(data.get("userUuid", "")).strip()
    hwid = str(data.get("hwid", "")).strip()
    if not uuid or not hwid:
        return {"ok": False, "error": "userUuid and hwid required"}
    try:
        user_id = int(uuid)
    except (TypeError, ValueError):
        return {"ok": False, "error": "invalid userUuid"}
    ok, msg = _api_post("/api/hwid/devices/delete", {"userId": user_id, "hwid": hwid})
    return {"ok": ok, "message": "Устройство удалено." if ok else msg}
