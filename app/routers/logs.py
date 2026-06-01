"""Endpoints de logs: eventos estruturados + tail do arquivo de log."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import select

from ..auth import require_auth
from ..config import LOG_FILE
from ..database import get_session
from ..models import Event

router = APIRouter(prefix="/api/logs", tags=["logs"], dependencies=[Depends(require_auth)])


@router.get("/events")
def list_events(
    target_id: Optional[int] = None,
    type: Optional[str] = None,
    limit: int = Query(default=100, le=500),
):
    with get_session() as s:
        stmt = select(Event).order_by(Event.created_at.desc())
        if target_id is not None:
            stmt = stmt.where(Event.target_id == target_id)
        if type:
            stmt = stmt.where(Event.type == type)
        stmt = stmt.limit(limit)
        rows = s.exec(stmt).all()
    return [
        {
            "id": e.id,
            "target_id": e.target_id,
            "target_name": e.target_name,
            "type": e.type,
            "message": e.message,
            "created_at": e.created_at.isoformat(),
        }
        for e in rows
    ]


@router.get("/raw")
def raw_log(lines: int = Query(default=200, le=2000)):
    """Últimas N linhas do arquivo de log (logs da aplicação/scraper)."""
    if not LOG_FILE.exists():
        return {"lines": []}
    with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
        content = f.readlines()
    return {"lines": [ln.rstrip("\n") for ln in content[-lines:]]}
