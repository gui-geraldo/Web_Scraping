"""Lógica de checagem de um alvo: busca, extrai, compara hash e alerta."""
from __future__ import annotations

import difflib
import hashlib
import html
import re
from datetime import datetime

from .database import get_session, get_setting, log_event
from .logging_conf import get_logger
from .models import Event, EventType, Target
from .scraper import browser_manager
from .telegram import send_message

logger = get_logger("monitor")


def _normalize(text: str) -> str:
    """Colapsa espaços/quebras para evitar falsos positivos por formatação."""
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()


def _diff_snippet(old: str, new: str, max_lines: int = 12) -> str:
    diff = difflib.unified_diff(
        (old or "").splitlines(),
        (new or "").splitlines(),
        lineterm="",
        n=1,
    )
    lines = [ln for ln in diff if ln and ln[0] in "+-" and not ln.startswith(("+++", "---"))]
    return "\n".join(lines[:max_lines])


async def check_target(target_id: int) -> None:
    """Executa uma checagem do alvo e dispara alerta se o conteúdo mudou."""
    with get_session() as s:
        target = s.get(Target, target_id)
        if not target or not target.enabled:
            return
        # Cópia dos campos necessários (a sessão fecha antes do await longo).
        t_id = target.id
        name = target.name
        url = target.url
        selector = target.selector
        extract_mode = target.extract_mode
        proxy = target.proxy or get_setting("global_proxy") or None
        previous_hash = target.last_hash
        previous_content = target.last_content or ""

    logger.info("Checando alvo #%s (%s)", t_id, name)
    result = await browser_manager.fetch(
        url, proxy=proxy, selector=selector, extract_mode=extract_mode
    )

    now = datetime.utcnow()

    if not result.ok:
        _persist_error(t_id, result.error or "erro desconhecido", now)
        log_event(EventType.error, f"Erro ao checar: {result.error}", t_id, name)
        return

    content = _normalize(result.text)
    if not content:
        msg = f"Seletor '{selector}' não retornou conteúdo (status HTTP {result.status})."
        _persist_error(t_id, msg, now)
        log_event(EventType.error, msg, t_id, name)
        return

    new_hash = _hash(content)

    # Primeira checagem: só registra a linha de base, sem alertar.
    if not previous_hash:
        _persist_ok(t_id, new_hash, content, now, changed=False)
        log_event(EventType.info, "Linha de base capturada (primeira checagem).", t_id, name)
        return

    if new_hash == previous_hash:
        _persist_ok(t_id, new_hash, content, now, changed=False)
        return

    # Mudou!
    _persist_ok(t_id, new_hash, content, now, changed=True)
    snippet = _diff_snippet(previous_content, content)
    log_event(EventType.change, "Conteúdo alterado.", t_id, name)
    logger.info("ALTERAÇÃO detectada no alvo #%s (%s)", t_id, name)

    await _alert(t_id, name, url, snippet)


async def _alert(target_id: int, name: str, url: str, snippet: str) -> None:
    body = (
        f"🔔 <b>Mudança detectada</b>\n"
        f"<b>{html.escape(name)}</b>\n"
        f"{html.escape(url)}\n"
    )
    if snippet:
        body += f"\n<pre>{html.escape(snippet)[:1500]}</pre>"
    ok, detail = await send_message(body)
    if ok:
        log_event(EventType.alert, "Alerta enviado ao Telegram.", target_id, name)
    else:
        log_event(EventType.error, f"Falha ao enviar alerta: {detail}", target_id, name)


def _persist_ok(target_id, new_hash, content, now, changed: bool) -> None:
    with get_session() as s:
        t = s.get(Target, target_id)
        if not t:
            return
        t.last_hash = new_hash
        t.last_content = content[:20000]
        t.last_checked_at = now
        t.last_status = "changed" if changed else "ok"
        t.last_error = None
        if changed:
            t.last_changed_at = now
        s.add(t)
        s.commit()


def _persist_error(target_id, error, now) -> None:
    with get_session() as s:
        t = s.get(Target, target_id)
        if not t:
            return
        t.last_checked_at = now
        t.last_status = "error"
        t.last_error = str(error)[:1000]
        s.add(t)
        s.commit()
