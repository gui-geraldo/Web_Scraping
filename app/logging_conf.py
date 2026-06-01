"""Configuração de logging: console + arquivo rotativo em DATA_DIR."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import LOG_FILE

_configured = False


def setup_logging() -> None:
    global _configured
    if _configured:
        return

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # Reduz o ruído de bibliotecas de terceiros.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
