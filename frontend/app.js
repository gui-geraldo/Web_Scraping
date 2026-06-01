"use strict";

// ---------- Auth / API helper ----------
const TOKEN_KEY = "vigia_token";
let authEnabled = false;

function getToken() { return localStorage.getItem(TOKEN_KEY) || ""; }
function setToken(t) { localStorage.setItem(TOKEN_KEY, t); }

async function api(path, opts = {}) {
  opts.headers = opts.headers || {};
  if (opts.body && !(opts.headers["Content-Type"])) {
    opts.headers["Content-Type"] = "application/json";
  }
  if (authEnabled) opts.headers["X-Access-Token"] = getToken();
  const res = await fetch(path, opts);
  if (res.status === 401) { showAuthModal(); throw new Error("401"); }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
}

// ---------- Tabs ----------
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById("tab-" + tab.dataset.tab).classList.add("active");
    if (tab.dataset.tab === "settings") loadSettings();
    if (tab.dataset.tab === "logs") loadLogs();
  });
});

// ---------- Targets ----------
const $ = (id) => document.getElementById(id);

function statusBadge(t) {
  if (!t.enabled) return `<span class="status off">desativado</span>`;
  const s = t.last_status;
  if (s === "ok") return `<span class="status ok">sem mudança</span>`;
  if (s === "changed") return `<span class="status changed">alterado</span>`;
  if (s === "error") return `<span class="status error">erro</span>`;
  return `<span class="status pending">aguardando</span>`;
}

function fmt(dt) {
  if (!dt) return "—";
  // Timestamps vêm em UTC sem fuso; marca como 'Z' para o navegador converter ao horário local.
  if (typeof dt === "string" && !/[zZ]|[+-]\d{2}:?\d{2}$/.test(dt)) dt += "Z";
  return new Date(dt).toLocaleString("pt-BR");
}

function intervalText(sec) {
  if (sec % 3600 === 0) return (sec / 3600) + "h";
  if (sec % 60 === 0) return (sec / 60) + "min";
  return sec + "s";
}

async function loadTargets() {
  const list = $("targets-list");
  try {
    const targets = await api("/api/targets");
    $("targets-empty").classList.toggle("hidden", targets.length > 0);
    list.innerHTML = targets.map((t) => `
      <div class="card target-card">
        <div class="top">
          <div>
            <h3>${esc(t.name)} ${statusBadge(t)}</h3>
            <div class="url"><a href="${esc(t.url)}" target="_blank" rel="noopener">${esc(t.url)}</a></div>
          </div>
        </div>
        <div class="meta">
          <span>🎯 <code>${esc(t.selector)}</code></span>
          <span>⏱️ ${intervalText(t.interval_seconds)}</span>
          <span>🔎 ${fmt(t.last_checked_at)}</span>
          ${t.last_changed_at ? `<span>🔔 mudou ${fmt(t.last_changed_at)}</span>` : ""}
        </div>
        ${t.last_error ? `<div class="muted" style="color:#f87171">${esc(t.last_error)}</div>` : ""}
        <div class="actions">
          <button class="btn small" onclick="runNow(${t.id})">▶ Checar agora</button>
          <button class="btn small" onclick="editTarget(${t.id})">✎ Editar</button>
          <button class="btn small" onclick="toggleTarget(${t.id}, ${!t.enabled})">${t.enabled ? "⏸ Pausar" : "▶ Ativar"}</button>
          <button class="btn small danger" onclick="deleteTarget(${t.id})">🗑 Excluir</button>
        </div>
      </div>`).join("");
  } catch (e) { /* auth */ }
}

let TARGETS_CACHE = [];

async function refreshCache() {
  TARGETS_CACHE = await api("/api/targets");
  return TARGETS_CACHE;
}

window.runNow = async (id) => {
  try { await api(`/api/targets/${id}/run`, { method: "POST" }); toast("Checagem disparada."); }
  catch (e) { toast("Erro: " + e.message); }
};

window.toggleTarget = async (id, enabled) => {
  const t = (await api(`/api/targets/${id}`));
  t.enabled = enabled;
  await api(`/api/targets/${id}`, { method: "PUT", body: JSON.stringify(toPayload(t)) });
  loadTargets();
};

window.deleteTarget = async (id) => {
  if (!confirm("Excluir este alvo?")) return;
  await api(`/api/targets/${id}`, { method: "DELETE" });
  loadTargets();
};

window.editTarget = async (id) => {
  const t = await api(`/api/targets/${id}`);
  openModal(t);
};

function toPayload(t) {
  return {
    name: t.name, url: t.url, selector: t.selector || "body",
    extract_mode: t.extract_mode, interval_seconds: t.interval_seconds,
    proxy: t.proxy || null, enabled: t.enabled,
  };
}

// ---------- Modal de alvo ----------
function openModal(t) {
  $("modal-title").textContent = t ? "Editar alvo" : "Novo alvo";
  $("f-id").value = t ? t.id : "";
  $("f-name").value = t ? t.name : "";
  $("f-url").value = t ? t.url : "";
  $("f-selector").value = t ? t.selector : "body";
  $("f-mode").value = t ? t.extract_mode : "text";
  $("f-proxy").value = t && t.proxy ? t.proxy : "";
  $("f-enabled").checked = t ? t.enabled : true;
  $("test-result").textContent = "";

  let sec = t ? t.interval_seconds : 300;
  let unit = 60;
  if (sec % 3600 === 0) unit = 3600; else if (sec % 60 === 0) unit = 60; else unit = 1;
  $("f-interval").value = sec / unit;
  $("f-interval-unit").value = String(unit);

  $("modal").classList.remove("hidden");
}

function closeModal() { $("modal").classList.add("hidden"); }

function formPayload() {
  const unit = parseInt($("f-interval-unit").value, 10);
  const interval = Math.max(1, parseInt($("f-interval").value, 10) || 1) * unit;
  return {
    name: $("f-name").value.trim(),
    url: $("f-url").value.trim(),
    selector: $("f-selector").value.trim() || "body",
    extract_mode: $("f-mode").value,
    interval_seconds: interval,
    proxy: $("f-proxy").value.trim() || null,
    enabled: $("f-enabled").checked,
  };
}

$("btn-add").onclick = () => openModal(null);
$("btn-cancel").onclick = closeModal;

$("btn-save-target").onclick = async () => {
  const payload = formPayload();
  if (!payload.name || !payload.url) { toast("Preencha nome e URL."); return; }
  const id = $("f-id").value;
  try {
    if (id) await api(`/api/targets/${id}`, { method: "PUT", body: JSON.stringify(payload) });
    else await api("/api/targets", { method: "POST", body: JSON.stringify(payload) });
    closeModal();
    loadTargets();
  } catch (e) { toast("Erro: " + e.message); }
};

$("btn-test-selector").onclick = async () => {
  const payload = formPayload();
  if (!payload.url) { toast("Informe a URL."); return; }
  $("test-result").textContent = "Testando...";
  try {
    const r = await api("/api/picker/test", { method: "POST", body: JSON.stringify({
      url: payload.url, selector: payload.selector, extract_mode: payload.extract_mode, proxy: payload.proxy,
    })});
    if (!r.ok) { $("test-result").textContent = "Falhou: " + r.message; return; }
    if (r.empty) { $("test-result").textContent = "Seletor não retornou conteúdo."; return; }
    $("test-result").textContent = `OK (${r.length} caracteres): "${r.content.slice(0, 120)}…"`;
  } catch (e) { $("test-result").textContent = "Erro: " + e.message; }
};

// ---------- Picker visual ----------
$("btn-pick").onclick = () => {
  const url = $("f-url").value.trim();
  if (!url) { toast("Informe a URL primeiro."); return; }
  const proxy = $("f-proxy").value.trim();
  let src = `/api/picker/render?url=${encodeURIComponent(url)}`;
  if (proxy) src += `&proxy=${encodeURIComponent(proxy)}`;
  if (authEnabled) src += `&token=${encodeURIComponent(getToken())}`;
  $("picker-frame").src = src;
  $("picker").classList.remove("hidden");
};

$("picker-close").onclick = () => {
  $("picker").classList.add("hidden");
  $("picker-frame").src = "about:blank";
};

window.addEventListener("message", (ev) => {
  const d = ev.data;
  if (d && d.__vigia && d.selector) {
    $("f-selector").value = d.selector;
    $("picker").classList.add("hidden");
    $("picker-frame").src = "about:blank";
    toast("Seletor capturado: " + d.selector);
  }
});

// ---------- Configurações ----------
async function loadSettings() {
  try {
    const s = await api("/api/settings");
    $("set-chat").value = s.telegram_chat_id || "";
    $("set-proxy").value = s.global_proxy || "";
    $("set-token").value = "";
    $("token-status").textContent = s.telegram_bot_token_set
      ? `Token salvo: ${s.telegram_bot_token_masked} (deixe vazio para manter)`
      : "Nenhum token salvo.";
  } catch (e) {}
  // Monta o link do noVNC apontando para o mesmo host, porta 6080.
  const vnc = $("btn-solve-vnc");
  if (vnc) vnc.href = `http://${location.hostname}:6080/vnc.html?autoconnect=1&resize=scale`;
}

// ---------- Captcha manual (VNC) ----------
$("btn-solve-start").onclick = async () => {
  const url = $("solve-url").value.trim() || "https://www.infojobs.net";
  $("solve-msg").textContent = "Abrindo navegador no servidor...";
  try {
    const r = await api("/api/solve/start", { method: "POST", body: JSON.stringify({ url }) });
    $("solve-msg").textContent = r.message + " → agora clique em 'Abrir VNC'.";
  } catch (e) { $("solve-msg").textContent = "Erro: " + e.message; }
};

$("btn-solve-save").onclick = async () => {
  $("solve-msg").textContent = "Salvando sessão...";
  try {
    const r = await api("/api/solve/close", { method: "POST" });
    $("solve-msg").textContent = r.message;
  } catch (e) { $("solve-msg").textContent = "Erro: " + e.message; }
};

$("btn-save-settings").onclick = async () => {
  const body = {
    telegram_chat_id: $("set-chat").value.trim(),
    global_proxy: $("set-proxy").value.trim(),
  };
  const token = $("set-token").value.trim();
  if (token) body.telegram_bot_token = token;
  try {
    await api("/api/settings", { method: "PUT", body: JSON.stringify(body) });
    $("settings-msg").textContent = "Salvo!";
    loadSettings();
  } catch (e) { $("settings-msg").textContent = "Erro: " + e.message; }
};

$("btn-test-telegram").onclick = async () => {
  $("settings-msg").textContent = "Testando...";
  // Salva antes de testar para usar credenciais atuais.
  await $("btn-save-settings").onclick();
  try {
    const r = await api("/api/settings/test-telegram", { method: "POST" });
    $("settings-msg").textContent = r.message;
  } catch (e) { $("settings-msg").textContent = "Erro: " + e.message; }
};

// ---------- Logs ----------
let logMode = "events";

async function loadLogs() {
  const box = $("logs-content");
  try {
    if (logMode === "events") {
      const events = await api("/api/logs/events?limit=200");
      box.innerHTML = events.map((e) => `
        <div class="log-line">
          <span class="log-time">${fmt(e.created_at)}</span>
          <span class="tag ${e.type}">${e.type.toUpperCase()}</span>
          ${e.target_name ? `<b>${esc(e.target_name)}</b> — ` : ""}${esc(e.message)}
        </div>`).join("") || "<div class='muted'>Sem eventos ainda.</div>";
    } else {
      const r = await api("/api/logs/raw?lines=400");
      box.textContent = r.lines.join("\n") || "Sem logs.";
    }
  } catch (e) {}
}

$("btn-log-events").onclick = () => { logMode = "events"; loadLogs(); };
$("btn-log-raw").onclick = () => { logMode = "raw"; loadLogs(); };
$("btn-log-refresh").onclick = loadLogs;

// ---------- Auth modal ----------
function showAuthModal() { $("auth-modal").classList.remove("hidden"); }
$("auth-submit").onclick = () => {
  setToken($("auth-token").value.trim());
  $("auth-modal").classList.add("hidden");
  init();
};

// ---------- Utils ----------
function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
let toastTimer;
function toast(msg) {
  let el = $("toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    el.style.cssText = "position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#1c2230;border:1px solid #2a3140;color:#e6edf3;padding:10px 16px;border-radius:8px;z-index:999;font-size:14px;box-shadow:0 4px 12px rgba(0,0,0,.4)";
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.style.opacity = "1";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity .4s"; }, 2600);
}

// ---------- Init ----------
async function init() {
  try {
    const cfg = await fetch("/api/config").then((r) => r.json());
    authEnabled = cfg.auth_enabled;
    if (authEnabled && !getToken()) { showAuthModal(); return; }
    await loadTargets();
    // Atualiza a lista de alvos periodicamente.
    setInterval(() => {
      if (document.getElementById("tab-targets").classList.contains("active")) loadTargets();
    }, 15000);
  } catch (e) { console.error(e); }
}

init();
