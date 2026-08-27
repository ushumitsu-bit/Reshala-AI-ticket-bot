import hashlib
import hmac
import json
import time
import urllib.parse
from unittest.mock import patch

import pytest
from fastapi import HTTPException

import middleware.auth as auth

TOKEN = "123456:ABC-DEF"


def make_init_data(user_id, auth_ts, token=TOKEN):
    user = json.dumps({"id": user_id, "first_name": "Test"})
    data = {"auth_date": str(auth_ts), "user": user}
    check = "\n".join(f"{k}={data[k]}" for k in sorted(data.keys()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(data)


async def test_valid_init_data_accepted():
    with patch("middleware.auth.get_bot_token", return_value=TOKEN):
        res = await auth.verify_telegram_auth(
            x_telegram_init_data=make_init_data(1, int(time.time()))
        )
    assert res["id"] == 1


async def test_invalid_signature_rejected():
    with patch("middleware.auth.get_bot_token", return_value=TOKEN):
        bad = make_init_data(1, int(time.time())).replace("hash=", "hash=deadbeef")
        with pytest.raises(HTTPException) as exc:
            await auth.verify_telegram_auth(x_telegram_init_data=bad)
    assert exc.value.status_code == 403


async def test_expired_init_data_rejected():
    with patch("middleware.auth.get_bot_token", return_value=TOKEN):
        old = make_init_data(1, int(time.time()) - 100000)
        with pytest.raises(HTTPException) as exc:
            await auth.verify_telegram_auth(x_telegram_init_data=old)
    assert exc.value.status_code == 403


async def test_require_manager_denies_non_manager():
    with patch("middleware.auth.get_settings", return_value={"allowed_manager_ids": [1, 2]}):
        with pytest.raises(HTTPException) as exc:
            await auth.require_manager(user_data={"id": 999})
    assert exc.value.status_code == 403


async def test_require_manager_allows_manager():
    with patch("middleware.auth.get_settings", return_value={"allowed_manager_ids": [1, 2]}):
        res = await auth.require_manager(user_data={"id": 2})
    assert res["id"] == 2
