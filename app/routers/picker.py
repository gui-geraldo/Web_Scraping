"""Endpoints do picker visual e teste de seletor."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..auth import require_auth
from ..database import get_setting
from ..monitor import _normalize
from ..picker import render_for_picker
from ..scraper import browser_manager

router = APIRouter(prefix="/api/picker", tags=["picker"])


@router.get("/render", dependencies=[Depends(require_auth)])
async def render(url: str = Query(...), proxy: Optional[str] = None):
    """Renderiza a página alvo como snapshot navegável (para o iframe)."""
    effective_proxy = proxy or get_setting("global_proxy") or None
    ok, html = await render_for_picker(url, proxy=effective_proxy)
    return HTMLResponse(content=html, status_code=200 if ok else 502)


class TestIn(BaseModel):
    url: str
    selector: str = "body"
    extract_mode: str = "text"
    proxy: Optional[str] = None


@router.post("/test", dependencies=[Depends(require_auth)])
async def test_selector(data: TestIn):
    """Busca a página e devolve o conteúdo extraído pelo seletor informado."""
    effective_proxy = data.proxy or get_setting("global_proxy") or None
    result = await browser_manager.fetch(
        data.url,
        proxy=effective_proxy,
        selector=data.selector or "body",
        extract_mode=data.extract_mode,
    )
    if not result.ok:
        return {"ok": False, "message": result.error, "content": ""}
    content = _normalize(result.text)
    return {
        "ok": True,
        "status": result.status,
        "length": len(content),
        "content": content[:2000],
        "empty": not content,
    }
