"""Autenticação opcional por token (ACCESS_TOKEN)."""
from __future__ import annotations

from fastapi import HTTPException, Request

from .config import ACCESS_TOKEN


def _extract_token(request: Request) -> str:
    header = request.headers.get("X-Access-Token")
    if header:
        return header
    return request.query_params.get("token", "")


async def require_auth(request: Request) -> None:
    """Dependência: exige token se ACCESS_TOKEN estiver configurado."""
    if not ACCESS_TOKEN:
        return
    if _extract_token(request) != ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail="Token inválido ou ausente.")


def auth_enabled() -> bool:
    return bool(ACCESS_TOKEN)
