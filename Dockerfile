# Imagem oficial da Playwright já vem com Chromium + todas as libs do sistema.
# A tag DEVE bater com a versão do pacote playwright no requirements.txt.
FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data \
    DISPLAY=:99

WORKDIR /app

# Xvfb: display virtual para rodar o Chromium em modo gráfico (headful) num
# servidor sem tela — bem menos detectável por anti-bots (DataDome/Cloudflare).
# x11vnc + noVNC + fluxbox: permitem acessar esse display pelo navegador (web)
# para resolver um captcha manualmente quando necessário.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        xvfb x11vnc novnc websockify fluxbox \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY frontend ./frontend
COPY start.sh ./start.sh
# Normaliza quebras de linha (caso editado no Windows) e torna executável.
RUN sed -i 's/\r$//' /app/start.sh && chmod +x /app/start.sh

# Diretório persistente para banco de dados e logs
RUN mkdir -p /data
VOLUME ["/data"]

# 8000 = interface/API   |   6080 = acesso VNC pelo navegador (noVNC)
EXPOSE 8000 6080

CMD ["bash", "/app/start.sh"]
