"""Configuração central da aplicação (lida de variáveis de ambiente)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Diretório de dados persistentes (banco SQLite + arquivo de log).
# No Docker é /data (volume). Localmente cai para ./data.
DATA_DIR = Path(os.getenv("DATA_DIR", str(Path(__file__).resolve().parent.parent / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "vigia.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

LOG_FILE = DATA_DIR / "vigia.log"

# Fuso horário usado pelo scheduler e nos timestamps.
TIMEZONE = os.getenv("TZ", "Europe/Madrid")

# Token opcional para proteger a UI. Vazio = sem autenticação.
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN", "").strip()

APP_PORT = int(os.getenv("APP_PORT", "8000"))

# Frequência mínima permitida (segundos) para evitar martelar os sites alvo.
MIN_INTERVAL_SECONDS = 30

# Jitter: variação aleatória aplicada a cada checagem para o intervalo não ser
# exato (ex.: 15min vira "15min ± alguns minutos"). É uma fração do intervalo,
# limitada por um teto, para parecer comportamento humano.
JITTER_FRACTION = 0.2          # 20% do intervalo
JITTER_MAX_SECONDS = 5 * 60    # nunca varia mais que 5 minutos para cada lado

# Pasta do frontend estático.
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
