"""Engine SQLite + helpers de sessão e configurações chave/valor."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from sqlmodel import Session, SQLModel, create_engine, select

from .config import DATABASE_URL
from .models import Event, EventType, Setting

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session() -> Iterator[Session]:
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


# ---- Configurações globais (tabela Setting) -------------------------------

def get_setting(key: str, default: str = "") -> str:
    with get_session() as s:
        obj = s.get(Setting, key)
        return obj.value if obj else default


def set_setting(key: str, value: str) -> None:
    with get_session() as s:
        obj = s.get(Setting, key)
        if obj:
            obj.value = value
        else:
            obj = Setting(key=key, value=value)
        s.add(obj)
        s.commit()


def get_all_settings() -> dict[str, str]:
    with get_session() as s:
        return {row.key: row.value for row in s.exec(select(Setting)).all()}


# ---- Eventos / log estruturado --------------------------------------------

def log_event(
    type: EventType | str,
    message: str,
    target_id: Optional[int] = None,
    target_name: Optional[str] = None,
) -> None:
    type_value = type.value if isinstance(type, EventType) else type
    with get_session() as s:
        s.add(
            Event(
                type=type_value,
                message=message,
                target_id=target_id,
                target_name=target_name,
            )
        )
        s.commit()
