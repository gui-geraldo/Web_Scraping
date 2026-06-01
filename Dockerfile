# Imagem oficial da Playwright já vem com Chromium + todas as libs do sistema.
# A tag DEVE bater com a versão do pacote playwright no requirements.txt.
FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY frontend ./frontend

# Diretório persistente para banco de dados e logs
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
