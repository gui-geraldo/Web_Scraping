"""Picker visual: renderiza a página alvo e injeta um seletor de elementos.

O HTML renderizado pela Playwright é servido pelo nosso próprio backend
(same-origin) dentro de um <iframe>. Um script injetado destaca o elemento
sob o cursor e, ao clicar, calcula um seletor CSS único e o envia ao app
pai via postMessage.
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from .logging_conf import get_logger
from .scraper import browser_manager

logger = get_logger("picker")

# CSS + JS injetados no snapshot para permitir a seleção visual.
PICKER_ASSETS = """
<style id="__vigia_picker_style">
  .__vigia_hover { outline: 2px solid #2f81f7 !important; outline-offset: -2px !important;
                   background: rgba(47,129,247,0.12) !important; cursor: crosshair !important; }
  .__vigia_selected { outline: 3px solid #1f9d55 !important; outline-offset: -3px !important;
                      background: rgba(31,157,85,0.18) !important; }
  #__vigia_bar { position: fixed; top: 0; left: 0; right: 0; z-index: 2147483647;
                 background: #0d1117; color: #e6edf3; font: 13px/1.4 system-ui, sans-serif;
                 padding: 8px 12px; box-shadow: 0 2px 8px rgba(0,0,0,.4); }
  #__vigia_bar b { color: #2f81f7; }
  html { scroll-padding-top: 44px; }
</style>
<div id="__vigia_bar">🎯 <b>Modo seleção:</b> passe o mouse e <b>clique</b> no elemento que deseja monitorar.</div>
<script id="__vigia_picker_js">
(function () {
  function cssPath(el) {
    if (!(el instanceof Element)) return '';
    if (el.id) return '#' + CSS.escape(el.id);
    var path = [];
    while (el && el.nodeType === 1 && el.tagName.toLowerCase() !== 'html') {
      var selector = el.tagName.toLowerCase();
      if (el.id) { selector = '#' + CSS.escape(el.id); path.unshift(selector); break; }
      var sib = el, nth = 1;
      while ((sib = sib.previousElementSibling)) {
        if (sib.tagName === el.tagName) nth++;
      }
      var sameTagSiblings = el.parentNode
        ? Array.prototype.filter.call(el.parentNode.children, function (c) { return c.tagName === el.tagName; })
        : [el];
      if (sameTagSiblings.length > 1) selector += ':nth-of-type(' + nth + ')';
      path.unshift(selector);
      el = el.parentElement;
    }
    return path.join(' > ');
  }

  var current = null;
  document.addEventListener('mouseover', function (e) {
    if (e.target.closest('#__vigia_bar')) return;
    if (current) current.classList.remove('__vigia_hover');
    current = e.target;
    current.classList.add('__vigia_hover');
  }, true);

  document.addEventListener('click', function (e) {
    if (e.target.closest('#__vigia_bar')) return;
    e.preventDefault();
    e.stopPropagation();
    var el = e.target;
    var selector = cssPath(el);
    document.querySelectorAll('.__vigia_selected').forEach(function (n) { n.classList.remove('__vigia_selected'); });
    el.classList.add('__vigia_selected');
    var sample = (el.innerText || '').trim().slice(0, 300);
    window.parent.postMessage({ __vigia: true, selector: selector, sample: sample }, '*');
  }, true);

  // Bloqueia navegação por links/formulários dentro do snapshot.
  document.addEventListener('submit', function (e) { e.preventDefault(); }, true);
})();
</script>
"""


def _sanitize(html: str, base_url: str) -> str:
    soup = BeautifulSoup(html, "lxml")

    # Remove scripts originais (evita redirecionamentos/anti-bot quebrando o snapshot).
    for tag in soup.find_all("script"):
        tag.decompose()
    # Remove handlers inline que poderiam navegar.
    for tag in soup.find_all(True):
        for attr in list(tag.attrs):
            if attr.lower().startswith("on"):
                del tag[attr]

    head = soup.head or soup.new_tag("head")
    if not soup.head:
        (soup.html or soup).insert(0, head)

    # <base> faz CSS/imagens relativas carregarem do site original.
    base = soup.new_tag("base", href=base_url)
    head.insert(0, base)

    # Injeta os assets do picker no fim do body.
    body = soup.body or soup
    picker = BeautifulSoup(PICKER_ASSETS, "lxml")
    for el in list(picker.contents):
        body.append(el)

    return str(soup)


async def render_for_picker(url: str, proxy: str | None = None) -> tuple[bool, str]:
    """Renderiza a URL e devolve (ok, html_para_iframe)."""
    result = await browser_manager.fetch(url, proxy=proxy)
    if not result.ok:
        msg = (
            "<html><body style='font:14px system-ui;padding:24px;color:#e6edf3;"
            "background:#0d1117'>"
            f"<h3>Não foi possível carregar a página</h3><p>{result.error or 'erro desconhecido'}</p>"
            "<p>Sites com anti-bot podem exigir um proxy. Configure um proxy nas "
            "Configurações ou no próprio alvo e tente novamente.</p></body></html>"
        )
        return False, msg
    return True, _sanitize(result.html, url)
