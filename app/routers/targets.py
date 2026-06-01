"""Endpoints CRUD dos alvos monitorados."""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from ..auth import require_auth
from ..config import MIN_INTERVAL_SECONDS
from ..database import get_session, log_event
from ..models import EventType, Target
from ..monitor import check_target
from ..scheduler import schedule_target, unschedule_target

router = APIRouter(prefix="/api/targets", tags=["targets"], dependencies=[Depends(require_auth)])


class TargetIn(BaseModel):
    name: str
    url: str
    selector: str = "body"
    extract_mode: str = "text"
    interval_seconds: int = 300
    proxy: Optional[str] = None
    enabled: bool = True


def _serialize(t: Target) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "url": t.url,
        "selector": t.selector,
        "extract_mode": t.extract_mode,
        "interval_seconds": t.interval_seconds,
        "proxy": t.proxy,
        "enabled": t.enabled,
        "last_status": t.last_status,
        "last_error": t.last_error,
        "last_checked_at": t.last_checked_at.isoformat() if t.last_checked_at else None,
        "last_changed_at": t.last_changed_at.isoformat() if t.last_changed_at else None,
        "last_content": (t.last_content or "")[:500],
    }


@router.get("")
def list_targets():
    with get_session() as s:
        return [_serialize(t) for t in s.exec(select(Target)).all()]


@router.post("")
def create_target(data: TargetIn):
    data.interval_seconds = max(data.interval_seconds, MIN_INTERVAL_SECONDS)
    with get_session() as s:
        t = Target(**data.model_dump())
        if not (t.selector or "").strip():
            t.selector = "body"
        s.add(t)
        s.commit()
        s.refresh(t)
        schedule_target(t)
        log_event(EventType.info, "Alvo criado.", t.id, t.name)
        return _serialize(t)


@router.get("/{target_id}")
def get_target(target_id: int):
    with get_session() as s:
        t = s.get(Target, target_id)
        if not t:
            raise HTTPException(404, "Alvo não encontrado.")
        return _serialize(t)


@router.put("/{target_id}")
def update_target(target_id: int, data: TargetIn):
    data.interval_seconds = max(data.interval_seconds, MIN_INTERVAL_SECONDS)
    with get_session() as s:
        t = s.get(Target, target_id)
        if not t:
            raise HTTPException(404, "Alvo não encontrado.")
        for k, v in data.model_dump().items():
            setattr(t, k, v)
        if not (t.selector or "").strip():
            t.selector = "body"
        s.add(t)
        s.commit()
        s.refresh(t)
        schedule_target(t)
        log_event(EventType.info, "Alvo atualizado.", t.id, t.name)
        return _serialize(t)


@router.delete("/{target_id}")
def delete_target(target_id: int):
    with get_session() as s:
        t = s.get(Target, target_id)
        if not t:
            raise HTTPException(404, "Alvo não encontrado.")
        name = t.name
        s.delete(t)
        s.commit()
    unschedule_target(target_id)
    log_event(EventType.info, f"Alvo removido ({name}).", target_id, name)
    return {"ok": True}


@router.post("/{target_id}/run")
async def run_now(target_id: int):
    """Dispara uma checagem imediata (assíncrona)."""
    with get_session() as s:
        if not s.get(Target, target_id):
            raise HTTPException(404, "Alvo não encontrado.")
    asyncio.create_task(check_target(target_id))
    return {"ok": True, "message": "Checagem disparada."}
