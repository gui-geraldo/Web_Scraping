"""Sessão manual de captcha via VNC.

Abre uma janela visível do Chromium (no display que o noVNC expõe), onde o
usuário resolve o desafio anti-bot à mão. Os cookies resultantes são salvos e
reaproveitados pelas checagens automáticas.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import require_auth
from ..database import get_setting
from ..logging_conf import get_logger
from ..scheduler import scheduler
from ..scraper import browser_manager

logger = get_logger("solve")

router = APIRouter(prefix="/api/solve", tags=["solve"], dependencies=[Depends(require_auth)])


class SolveIn(BaseModel):
    url: str = "https://www.infojobs.net"
    proxy: Optional[str] = None


def _pause_scheduler() -> None:
    # Evita que checagens automáticas abram janelas concorrentes durante o solve.
    try:
        if scheduler.running:
            scheduler.pause()
    except Exception:  # noqa: BLE001
        pass


def _resume_scheduler() -> None:
    try:
        scheduler.resume()
    except Exception:  # noqa: BLE001
        pass


@router.post("/start")
async def start(data: SolveIn):
    proxy = data.proxy or get_setting("global_proxy") or None
    _pause_scheduler()
    await browser_manager.open_manual_session(data.url, proxy=proxy)
    return {
        "ok": True,
        "message": "Navegador aberto no servidor. Conecte pelo VNC e resolva o captcha.",
    }


@router.post("/save")
async def save():
    await browser_manager.save_manual_session()
    return {"ok": True, "message": "Cookies da sessão salvos."}


@router.post("/close")
async def close():
    await browser_manager.close_manual_session(save=True)
    _resume_scheduler()
    return {"ok": True, "message": "Sessão encerrada e cookies salvos. Checagens retomadas."}


@router.get("/status")
async def status():
    return {"active": browser_manager.manual_active()}
