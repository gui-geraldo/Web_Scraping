"""Endpoints de configurações globais (Telegram, proxy)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import require_auth
from ..database import get_setting, set_setting
from ..telegram import test_credentials

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(require_auth)])

# Chaves expostas na UI. O token é mascarado na leitura.
KEYS = ["telegram_bot_token", "telegram_chat_id", "global_proxy"]


class SettingsIn(BaseModel):
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    global_proxy: Optional[str] = None


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "••••"
    return value[:4] + "••••" + value[-4:]


@router.get("")
def read_settings():
    token = get_setting("telegram_bot_token")
    return {
        "telegram_bot_token_set": bool(token),
        "telegram_bot_token_masked": _mask(token),
        "telegram_chat_id": get_setting("telegram_chat_id"),
        "global_proxy": get_setting("global_proxy"),
    }


@router.put("")
def update_settings(data: SettingsIn):
    # Só grava campos enviados (None = não mexe; útil para não apagar o token).
    if data.telegram_bot_token is not None and data.telegram_bot_token != "":
        set_setting("telegram_bot_token", data.telegram_bot_token.strip())
    if data.telegram_chat_id is not None:
        set_setting("telegram_chat_id", data.telegram_chat_id.strip())
    if data.global_proxy is not None:
        set_setting("global_proxy", data.global_proxy.strip())
    return read_settings()


@router.post("/test-telegram")
async def test_telegram():
    ok, detail = await test_credentials()
    return {"ok": ok, "message": detail}
