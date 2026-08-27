
import hashlib
import hmac
import json
import time
import urllib.parse
import os
from typing import Dict, Optional

from fastapi import Header, HTTPException, Depends, Request
from utils.db_config import get_bot_token, get_settings

async def verify_telegram_auth(
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
):
    """
    Validates Telegram WebApp initData.
    Expects header: X-Telegram-Init-Data
    """
    # SKIP_AUTH for local development/debugging
    skip_auth = os.environ.get("SKIP_AUTH", "false").lower() == "true"

    if not x_telegram_init_data:
        if skip_auth:
            # Return a dummy manager for development
            # Usually the first manager from ALLOWED_MANAGER_IDS
            from utils.db_config import get_settings
            config = get_settings()
            managers = config.get("allowed_manager_ids", [0])
            manager_id = managers[0] if managers else 0
            
            return {"id": manager_id, "first_name": "Dev", "last_name": "Manager", "username": "dev_manager"}
            
        raise HTTPException(status_code=401, detail="Missing X-Telegram-Init-Data header")

    bot_token = get_bot_token()
    if not bot_token:
        raise HTTPException(status_code=500, detail="Bot token not configured")

    try:
        parsed_data = urllib.parse.parse_qs(x_telegram_init_data)
        data_dict = {k: v[0] for k, v in parsed_data.items()}
        
        if "hash" not in data_dict:
            raise HTTPException(status_code=401, detail="Invalid initData: missing hash")

        hash_value = data_dict.pop("hash")
        
        # Sort keys alpha
        data_check_string = "\n".join(f"{k}={data_dict[k]}" for k in sorted(data_dict.keys()))
        
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        if calculated_hash != hash_value:
             raise HTTPException(status_code=403, detail="Invalid initData signature")

        # Проверка свежести initData (защита от replay)
        auth_date = data_dict.get("auth_date")
        if auth_date:
            try:
                auth_ts = int(auth_date)
            except (TypeError, ValueError):
                raise HTTPException(status_code=401, detail="Invalid initData: auth_date")
            ttl = int(os.environ.get("TELEGRAM_INITDATA_TTL", "86400"))
            if time.time() - auth_ts > ttl:
                raise HTTPException(status_code=403, detail="initData expired")

        # Parse user data if needed
        user_data = json.loads(data_dict.get("user", "{}"))
        return user_data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Auth failed: {str(e)}")


async def require_manager(user_data: dict = Depends(verify_telegram_auth)):
    """
    Проверяет, что пользователь является менеджером (его id в allowed_manager_ids).
    Вызывает verify_telegram_auth, затем сверяет user["id"] с allowed_manager_ids.
    В dev-режиме (SKIP_AUTH=true) поведение сохраняется — dummy-менеджер допускается.
    """
    skip_auth = os.environ.get("SKIP_AUTH", "false").lower() == "true"
    if skip_auth:
        return user_data

    user_id = user_data.get("id") if isinstance(user_data, dict) else None
    if user_id is None:
        raise HTTPException(status_code=403, detail="Access denied: not a manager")

    allowed = {str(x) for x in (get_settings().get("allowed_manager_ids") or [])}
    if str(user_id) not in allowed:
        raise HTTPException(status_code=403, detail="Access denied: not a manager")

    return user_data
