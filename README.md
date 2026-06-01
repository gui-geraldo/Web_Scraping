# 🛰️ Vigia — Monitor de Páginas (self-hosted)

Monitora **várias páginas ao mesmo tempo**, detecta mudanças no conteúdo
(sem nenhuma IA — apenas comparação de hash do texto) e envia **alertas pelo
Telegram**. Tudo com uma **interface web** para configurar os alvos, escolher
visualmente a **área** a monitorar (clicando no elemento), definir a
**frequência** e ver os **logs**.

Pensado para alvos com anti-bot pesado (Indeed, InfoJobs): usa um **navegador
real (Chromium via Playwright)** com técnicas de *stealth* e suporte a **proxy**.

100% auto-hospedável via Docker — feito para rodar numa máquina Linux dedicada.

---

## ✨ Recursos

- ✅ Monitoramento simultâneo de múltiplas páginas (cada uma com sua frequência).
- ✅ **Seleção visual**: cole a URL e clique no elemento que quer vigiar — o seletor CSS é gerado sozinho.
- ✅ Monitorar a **página inteira** (`body`) ou só uma **área** (seletor CSS).
- ✅ Detecção de mudança por hash do conteúdo (**sem IA**), com trecho do *diff* no alerta.
- ✅ Alertas via **Telegram** (token do BotFather + chat_id configuráveis na UI).
- ✅ Navegador real + stealth + **proxy** (global ou por alvo) para sites com anti-bot.
- ✅ **Logs** visíveis na interface (eventos estruturados + log bruto da aplicação).
- ✅ Banco SQLite local — sem serviços externos. Token de acesso opcional para a UI.

---

## 🚀 Início rápido (Docker — recomendado)

Pré-requisitos: **Docker** e **Docker Compose** na máquina Linux.

```bash
git clone <seu-repo> vigia && cd vigia      # ou copie a pasta para o servidor
cp .env.example .env                        # ajuste se quiser (porta, token, fuso)
docker compose up -d --build
```

Acesse: **http://IP-DA-MAQUINA:8000**

Os dados (banco + logs) ficam em `./data` (volume persistente).

Ver logs do container em tempo real:

```bash
docker compose logs -f
```

Atualizar depois de mudar o código:

```bash
docker compose up -d --build
```

---

## 🤖 Configurando o Telegram

1. No Telegram, fale com **@BotFather** → `/newbot` → siga os passos → copie o **token**.
2. Descubra seu **chat_id**:
   - Mande uma mensagem para o seu bot, depois abra no navegador:
     `https://api.telegram.org/bot<SEU_TOKEN>/getUpdates`
     e veja o campo `chat.id`. (Para grupos, adicione o bot ao grupo primeiro.)
3. Na aba **Configurações** da interface, cole o **token** e o **chat_id**, clique
   em **Salvar** e depois em **Testar Telegram** — você deve receber uma mensagem.

---

## 🎯 Adicionando um alvo

1. Aba **Alvos** → **+ Adicionar alvo**.
2. Informe **Nome** e **URL**.
3. Clique em **🎯 Selecionar visualmente** — a página é renderizada; passe o mouse
   e **clique** no bloco que deseja monitorar. O seletor CSS é preenchido sozinho.
   (Ou deixe `body` para a página inteira.)
4. Defina a **Frequência** (ex.: 5 minutos).
5. (Opcional) **Testar seletor** para ver o conteúdo que será capturado.
6. **Salvar alvo**. A primeira checagem captura a linha de base; a partir daí,
   qualquer mudança no conteúdo dispara um alerta no Telegram.

---

## 🌐 Anti-bot e proxy (Indeed / InfoJobs)

Esses sites usam proteções agressivas (Cloudflare, fingerprinting). O Vigia já
usa navegador real + stealth, mas em muitos casos o **fator decisivo é o IP**.
Se as checagens começarem a falhar ou cair em captcha:

- Configure um **proxy** (de preferência **residencial**) em **Configurações → Proxy global**,
  ou um proxy específico no formulário do alvo.
  Formato: `http://usuario:senha@host:porta`.
- Evite frequências muito altas (use minutos, não segundos) para não chamar atenção.

> A frequência mínima é 30s por padrão (configurável em `app/config.py`).
> As checagens também têm um **jitter** aleatório (o intervalo nunca é exato),
> para imitar comportamento humano.

### Resolver captcha manualmente (VNC)

O InfoJobs usa **DataDome**. O scraper já roda em modo gráfico (Xvfb) e tenta
liberar o desafio sozinho, mas se ele insistir você pode **resolver à mão uma vez**:

1. Aba **Configurações → Resolver captcha manualmente (VNC)**.
2. Clique em **1) Abrir navegador** (abre a página no servidor).
3. Clique em **2) Abrir VNC** — abre uma aba mostrando a tela do servidor
   (noVNC, porta **6080**). Resolva o captcha com o mouse.
4. Volte e clique em **3) Salvar e fechar**.

Os cookies (incl. o `datadome`) ficam salvos em `/data/browser_state.json` e as
checagens automáticas passam a reutilizá-los. Como o cookie fica **amarrado ao
IP do servidor**, é importante resolver **a partir do próprio servidor** (via
noVNC), e não do seu computador.

> 🔒 A porta 6080 dá controle do navegador do servidor. Em rede não confiável,
> defina `VNC_PASSWORD` no `.env`.

---

## 🔒 Acesso protegido (opcional)

Para exigir um token ao abrir a UI, defina `ACCESS_TOKEN` no `.env`:

```env
ACCESS_TOKEN=uma-senha-bem-grande
```

Reinicie (`docker compose up -d`). A interface pedirá o token no primeiro acesso.

---

## 📜 Logs

- **Aba Logs → Eventos**: histórico estruturado (criação de alvos, mudanças, alertas, erros).
- **Aba Logs → Log bruto**: as últimas linhas do log da aplicação/scraper.
- Arquivo em disco: `./data/vigia.log` (rotativo).

---

## 🛠️ Rodando sem Docker (desenvolvimento)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium          # baixa o navegador
playwright install-deps              # (Linux) instala libs do sistema
uvicorn app.main:app --reload --port 8000
```

---

## 🧱 Arquitetura

```
Frontend (HTML/CSS/JS puro)  ──>  FastAPI  ──>  SQLite (alvos, configs, eventos)
                                     │
                                     ├─ APScheduler  (1 job por alvo, na sua frequência)
                                     ├─ Playwright/Chromium + stealth + proxy
                                     └─ Telegram Bot API (alertas)
```

| Camada        | Tecnologia                          |
|---------------|-------------------------------------|
| API/Backend   | FastAPI + Uvicorn                   |
| Agendamento   | APScheduler (AsyncIOScheduler)      |
| Scraping      | Playwright (Chromium) + stealth     |
| Banco         | SQLite (SQLModel)                   |
| Frontend      | HTML/CSS/JS sem build               |
| Alertas       | Telegram Bot API (via httpx)        |
| Deploy        | Docker / Docker Compose             |

---

## ❓ Solução de problemas

- **"Seletor não retornou conteúdo"**: o site mudou o layout ou bloqueou o acesso.
  Reabra o seletor visual e escolha o elemento de novo; considere usar um proxy.
- **Alertas não chegam**: confira token/chat_id em Configurações e clique em *Testar Telegram*.
- **Muita RAM**: o Chromium consome bastante. Mantenha frequências razoáveis e poucos
  alvos simultâneos; o `shm_size` já está em 1GB no compose.
- **Container reinicia em loop**: veja `docker compose logs -f` para o erro exato.
