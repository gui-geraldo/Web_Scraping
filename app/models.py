"""Modelos de dados (SQLModel/SQLite)."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.utcnow()


class Target(SQLModel, table=True):
    """Uma página monitorada."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    url: str

    # Seletor CSS a monitorar. Vazio/"body" = página inteira.
    selector: str = Field(default="body")

    # Como interpretar o conteúdo extraído: "text" (innerText) ou "html".
    extract_mode: str = Field(default="text")

    # Intervalo entre checagens, em segundos.
    interval_seconds: int = Field(default=300)

    # Proxy específico deste alvo (sobrepõe o global). Ex: http://user:pass@host:port
    proxy: Optional[str] = Field(default=None)

    enabled: bool = Field(default=True)

    # Estado da última checagem
    last_hash: Optional[str] = Field(default=None)
    last_content: Optional[str] = Field(default=None)
    last_checked_at: Optional[datetime] = Field(default=None)
    last_changed_at: Optional[datetime] = Field(default=None)
    last_status: Optional[str] = Field(default=None)  # ok | error | changed
    last_error: Optional[str] = Field(default=None)

    created_at: datetime = Field(default_factory=utcnow)


class Setting(SQLModel, table=True):
    """Pares chave/valor para configurações globais (Telegram, proxy, etc.)."""

    key: str = Field(primary_key=True)
    value: str = Field(default="")


class EventType(str, Enum):
    info = "info"
    change = "change"
    error = "error"
    alert = "alert"


class Event(SQLModel, table=True):
    """Histórico de eventos / log estruturado por alvo."""

    id: Optional[int] = Field(default=None, primary_key=True)
    target_id: Optional[int] = Field(default=None, index=True)
    target_name: Optional[str] = Field(default=None)
    type: str = Field(default=EventType.info.value, index=True)
    message: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow, index=True)
