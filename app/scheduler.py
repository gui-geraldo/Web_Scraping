"""Agendamento das checagens com APScheduler (AsyncIOScheduler)."""
from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlmodel import select

from .config import (
    JITTER_FRACTION,
    JITTER_MAX_SECONDS,
    MIN_INTERVAL_SECONDS,
    TIMEZONE,
)
from .database import get_session
from .logging_conf import get_logger
from .models import Target
from .monitor import check_target

logger = get_logger("scheduler")


def _safe_timezone(name: str):
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        logger.warning("Fuso '%s' inválido — usando UTC.", name)
        return ZoneInfo("UTC")


scheduler = AsyncIOScheduler(timezone=_safe_timezone(TIMEZONE))


def _job_id(target_id: int) -> str:
    return f"target-{target_id}"


def schedule_target(target: Target) -> None:
    """(Re)agenda um alvo conforme seu intervalo. Remove se desabilitado."""
    job_id = _job_id(target.id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    if not target.enabled:
        logger.info("Alvo #%s desabilitado — não agendado.", target.id)
        return

    interval = max(int(target.interval_seconds), MIN_INTERVAL_SECONDS)
    # Variação aleatória (± jitter) aplicada a cada disparo: o intervalo nunca
    # é exato, imitando um humano. APScheduler sorteia um novo offset por execução.
    jitter = int(min(interval * JITTER_FRACTION, JITTER_MAX_SECONDS))
    scheduler.add_job(
        check_target,
        trigger="interval",
        seconds=interval,
        jitter=jitter,
        id=job_id,
        args=[target.id],
        max_instances=1,
        coalesce=True,
        replace_existing=True,
        misfire_grace_time=60,
    )
    logger.info(
        "Alvo #%s (%s) agendado a cada %ss (± %ss aleatórios).",
        target.id, target.name, interval, jitter,
    )


def unschedule_target(target_id: int) -> None:
    job_id = _job_id(target_id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info("Alvo #%s removido do agendador.", target_id)


def load_all_targets() -> None:
    """Agenda todos os alvos habilitados na inicialização."""
    with get_session() as s:
        targets = s.exec(select(Target)).all()
        for t in targets:
            schedule_target(t)
    logger.info("%d alvo(s) carregado(s) no agendador.", len(targets))


def start_scheduler() -> None:
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler iniciado.")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
