"""Envio de mensagens via Telegram Bot API (sem dependências pesadas)."""
from __future__ import annotations

import httpx

from .database import get_setting
from .logging_conf import get_logger

logger = get_logger("telegram")

API = "https://api.telegram.org/bot{token}/{method}"


def _credentials() -> tuple[str, str]:
    return get_setting("telegram_bot_token"), get_setting("telegram_chat_id")


async def send_message(text: str, *, parse_mode: str = "HTML") -> tuple[bool, str]:
    """Envia uma mensagem para o chat configurado. Retorna (ok, detalhe)."""
    token, chat_id = _credentials()
    if not token or not chat_id:
        return False, "Credenciais do Telegram não configuradas."

    url = API.format(token=token, method="sendMessage")
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload)
        data = resp.json()
        if resp.status_code == 200 and data.get("ok"):
            return True, "Mensagem enviada."
        detail = data.get("description", resp.text)
        logger.warning("Telegram recusou a mensagem: %s", detail)
        return False, f"Telegram: {detail}"
    except Exception as exc:  # noqa: BLE001
        logger.error("Erro ao enviar Telegram: %s", exc)
        return False, str(exc)


async def test_credentials() -> tuple[bool, str]:
    """Valida o token chamando getMe e tenta uma mensagem de teste."""
    token, chat_id = _credentials()
    if not token:
        return False, "Informe o token do bot."
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            me = await client.get(API.format(token=token, method="getMe"))
        data = me.json()
        if not (me.status_code == 200 and data.get("ok")):
            return False, "Token inválido."
        bot_name = data["result"].get("username", "?")
    except Exception as exc:  # noqa: BLE001
        return False, f"Erro de conexão: {exc}"

    if not chat_id:
        return True, f"Token OK (@{bot_name}). Informe o chat_id para receber alertas."

    ok, detail = await send_message(
        f"✅ <b>Vigia conectado</b>\nBot @{bot_name} pronto para enviar alertas."
    )
    return ok, detail if not ok else f"Tudo certo! Teste enviado por @{bot_name}."
