"""Scraper baseado em Playwright (Chromium) com técnicas de stealth.

Mantém UMA instância do navegador viva e abre um contexto novo a cada
checagem — isso renova o fingerprint (cookies, storage) e ajuda contra
mecanismos anti-bot de sites como Indeed e InfoJobs.

Toda a API é assíncrona e roda no mesmo event loop do FastAPI/APScheduler.
"""
from __future__ import annotations

import asyncio
import os
import random
from dataclasses import dataclass
from typing import Optional

from playwright.async_api import Browser, async_playwright

from .config import HEADLESS, STATE_FILE
from .logging_conf import get_logger

logger = get_logger("scraper")

# Marcadores que indicam uma tela de desafio anti-bot (DataDome/Cloudflare/etc).
CHALLENGE_MARKERS = [
    "eres humano",
    "hacer clic para comprobar",
    "just a moment",
    "verifying you are human",
    "captcha-delivery",
    "are you a robot",
    "_dd_challenge",
    "geo.captcha",
]

# User-Agents reais e recentes para rotação.
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

# Script injetado antes de qualquer script da página: esconde sinais de automação.
STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR', 'pt', 'es', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = { runtime: {}, app: {}, csi: function(){}, loadTimes: function(){} };
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
  parameters.name === 'notifications'
    ? Promise.resolve({ state: Notification.permission })
    : originalQuery(parameters)
);
Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 4});
Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
  if (parameter === 37445) return 'Intel Inc.';
  if (parameter === 37446) return 'Intel Iris OpenGL Engine';
  return getParameter.call(this, parameter);
};
"""

LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
]


@dataclass
class FetchResult:
    ok: bool
    html: str = ""
    text: str = ""
    status: Optional[int] = None
    error: Optional[str] = None


class BrowserManager:
    """Gerencia o ciclo de vida do Chromium (singleton)."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._lock = asyncio.Lock()
        self._state_lock = asyncio.Lock()
        # Sessão manual (resolver captcha via VNC)
        self._manual_context = None
        self._manual_page = None

    async def start(self) -> None:
        if self._browser:
            return
        async with self._lock:
            if self._browser:
                return
            mode = "headless" if HEADLESS else "headful (gráfico/Xvfb)"
            logger.info("Iniciando Chromium (%s)...", mode)
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=HEADLESS,
                args=LAUNCH_ARGS,
            )
            logger.info("Chromium pronto.")

    async def stop(self) -> None:
        await self.close_manual_session(save=True)
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def _new_context(self, proxy: Optional[str]):
        assert self._browser is not None
        kwargs = dict(
            user_agent=random.choice(USER_AGENTS),
            # Fingerprint coerente com o IP de saída (residencial brasileiro).
            # 'es' entra como idioma secundário — plausível para quem busca vagas na Espanha.
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1366, "height": 768},
            ignore_https_errors=True,
            extra_http_headers={
                "Accept-Language": "pt-BR,pt;q=0.9,es;q=0.8,en;q=0.7",
            },
        )
        if proxy:
            kwargs["proxy"] = _parse_proxy(proxy)
        # Reaproveita a sessão salva (cookies do DataDome etc.) se existir.
        if STATE_FILE.exists():
            kwargs["storage_state"] = str(STATE_FILE)
        context = await self._browser.new_context(**kwargs)
        await context.add_init_script(STEALTH_JS)
        return context

    async def _save_state(self, context) -> None:
        """Persiste cookies/localStorage para reusar a sessão (evita captcha repetido)."""
        async with self._state_lock:
            try:
                tmp = STATE_FILE.with_suffix(".tmp")
                await context.storage_state(path=str(tmp))
                os.replace(tmp, STATE_FILE)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Não foi possível salvar o estado do navegador: %s", exc)

    async def fetch(
        self,
        url: str,
        proxy: Optional[str] = None,
        selector: Optional[str] = None,
        extract_mode: str = "text",
        timeout_ms: int = 45000,
    ) -> FetchResult:
        """Carrega a URL e devolve HTML completo + conteúdo extraído do seletor."""
        await self.start()
        context = None
        try:
            context = await self._new_context(proxy)
            page = await context.new_page()
            response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            status = response.status if response else None

            # Pequena espera para conteúdo dinâmico + simula comportamento humano.
            await page.wait_for_timeout(random.randint(1500, 3500))
            try:
                await page.mouse.move(random.randint(100, 800), random.randint(100, 500))
                await page.evaluate("window.scrollBy(0, document.body.scrollHeight/3)")
                await page.wait_for_timeout(800)
            except Exception:
                pass

            # Se houver desafio anti-bot, tenta liberar antes de extrair.
            passed = await self._maybe_solve_challenge(page)

            html = await page.content()
            sel = (selector or "").strip() or "body"
            extracted = await self._extract(page, sel, extract_mode)

            # Salva a sessão (cookies) para a próxima checagem não cair no captcha.
            await self._save_state(context)

            if not passed:
                return FetchResult(
                    ok=False,
                    html=html,
                    status=status,
                    error="Desafio anti-bot (captcha) não foi liberado automaticamente.",
                )
            return FetchResult(ok=True, html=html, text=extracted, status=status)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao carregar %s: %s", url, exc)
            return FetchResult(ok=False, error=str(exc))
        finally:
            if context:
                await context.close()

    async def _is_challenged(self, page) -> bool:
        try:
            title = (await page.title()).lower()
        except Exception:
            title = ""
        try:
            body = (await page.content()).lower()
        except Exception:
            body = ""
        haystack = f"{title} {body[:5000]}"
        return any(marker in haystack for marker in CHALLENGE_MARKERS)

    async def _maybe_solve_challenge(self, page, max_wait_s: int = 30) -> bool:
        """Detecta desafio anti-bot, tenta clicar e aguarda liberar. True se passou."""
        if not await self._is_challenged(page):
            return True
        logger.warning("Desafio anti-bot detectado em %s — tentando liberar...", page.url)
        await self._try_click_challenge(page)
        # Aguarda a liberação automática (DataDome costuma liberar p/ navegador convincente).
        for _ in range(max_wait_s // 2):
            await page.wait_for_timeout(2000)
            if not await self._is_challenged(page):
                logger.info("Desafio liberado com sucesso.")
                return True
        logger.warning("Desafio anti-bot persistiu — conteúdo pode vir vazio/captcha.")
        return False

    async def _try_click_challenge(self, page) -> None:
        """Tentativa best-effort de clicar no botão/checkbox do desafio."""
        selectors = [
            "text=Hacer clic para comprobar",
            ".ctp-checkbox-label",
            "input[type=checkbox]",
            "#ddv1-captcha-container",
        ]
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click(timeout=3000)
                    await page.wait_for_timeout(2000)
                    return
            except Exception:
                continue
        # DataDome serve o captcha dentro de um iframe (captcha-delivery.com).
        for frame in page.frames:
            if "captcha-delivery" in (frame.url or ""):
                for sel in [".ctp-checkbox-label", "input[type=checkbox]", "button"]:
                    try:
                        await frame.locator(sel).first.click(timeout=3000)
                        await page.wait_for_timeout(2000)
                        return
                    except Exception:
                        continue

    # ---- Sessão manual (VNC) ------------------------------------------------

    async def open_manual_session(self, url: str, proxy: Optional[str] = None) -> None:
        """Abre uma janela visível (no display VNC) navegando até a URL.

        O usuário resolve o captcha pelo noVNC; depois chama save/close para
        gravar os cookies da sessão.
        """
        await self.start()
        await self.close_manual_session(save=False)
        self._manual_context = await self._new_context(proxy)
        self._manual_page = await self._manual_context.new_page()
        logger.info("Sessão manual aberta — navegando até %s", url)
        try:
            await self._manual_page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sessão manual: falha ao navegar: %s", exc)

    async def save_manual_session(self) -> None:
        if self._manual_context:
            await self._save_state(self._manual_context)
            logger.info("Sessão manual: cookies salvos.")

    async def close_manual_session(self, save: bool = True) -> None:
        if self._manual_context:
            if save:
                try:
                    await self._save_state(self._manual_context)
                    logger.info("Sessão manual: cookies salvos.")
                except Exception:  # noqa: BLE001
                    pass
            try:
                await self._manual_context.close()
            except Exception:  # noqa: BLE001
                pass
        self._manual_context = None
        self._manual_page = None

    def manual_active(self) -> bool:
        return self._manual_context is not None

    async def _extract(self, page, selector: str, extract_mode: str) -> str:
        try:
            locator = page.locator(selector).first
            count = await page.locator(selector).count()
            if count == 0:
                return ""
            if extract_mode == "html":
                return await locator.inner_html()
            return await locator.inner_text()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao extrair seletor %r: %s", selector, exc)
            return ""


def _parse_proxy(proxy: str) -> dict:
    """Converte 'http://user:pass@host:port' no formato esperado pela Playwright."""
    proxy = proxy.strip()
    server = proxy
    username = None
    password = None
    if "@" in proxy:
        scheme = ""
        rest = proxy
        if "://" in proxy:
            scheme, rest = proxy.split("://", 1)
            scheme += "://"
        creds, hostpart = rest.rsplit("@", 1)
        if ":" in creds:
            username, password = creds.split(":", 1)
        else:
            username = creds
        server = f"{scheme}{hostpart}"
    result = {"server": server}
    if username:
        result["username"] = username
    if password:
        result["password"] = password
    return result


# Instância global compartilhada.
browser_manager = BrowserManager()
