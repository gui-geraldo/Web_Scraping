"""Scraper baseado em Playwright (Chromium) com técnicas de stealth.

Mantém UMA instância do navegador viva e abre um contexto novo a cada
checagem — isso renova o fingerprint (cookies, storage) e ajuda contra
mecanismos anti-bot de sites como Indeed e InfoJobs.

Toda a API é assíncrona e roda no mesmo event loop do FastAPI/APScheduler.
"""
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Optional

from playwright.async_api import Browser, async_playwright

from .logging_conf import get_logger

logger = get_logger("scraper")

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
Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR', 'pt', 'en-US', 'en']});
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

    async def start(self) -> None:
        if self._browser:
            return
        async with self._lock:
            if self._browser:
                return
            logger.info("Iniciando Chromium (Playwright)...")
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=LAUNCH_ARGS,
            )
            logger.info("Chromium pronto.")

    async def stop(self) -> None:
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
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1366, "height": 768},
            ignore_https_errors=True,
            extra_http_headers={
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            },
        )
        if proxy:
            kwargs["proxy"] = _parse_proxy(proxy)
        context = await self._browser.new_context(**kwargs)
        await context.add_init_script(STEALTH_JS)
        return context

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

            html = await page.content()

            sel = (selector or "").strip() or "body"
            extracted = await self._extract(page, sel, extract_mode)

            return FetchResult(ok=True, html=html, text=extracted, status=status)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao carregar %s: %s", url, exc)
            return FetchResult(ok=False, error=str(exc))
        finally:
            if context:
                await context.close()

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
