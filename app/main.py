"""Aplicação FastAPI: API + frontend + ciclo de vida (scraper/scheduler)."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .auth import auth_enabled
from .config import FRONTEND_DIR
from .database import init_db
from .logging_conf import get_logger, setup_logging
from .routers import logs, picker, settings, solve, targets
from .scheduler import load_all_targets, start_scheduler, stop_scheduler
from .scraper import browser_manager

setup_logging()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando Vigia...")
    init_db()
    await browser_manager.start()
    start_scheduler()
    load_all_targets()
    logger.info("Vigia pronto.")
    yield
    logger.info("Encerrando Vigia...")
    stop_scheduler()
    await browser_manager.stop()


app = FastAPI(title="Vigia — Monitor de Páginas", lifespan=lifespan)

app.include_router(targets.router)
app.include_router(settings.router)
app.include_router(logs.router)
app.include_router(picker.router)
app.include_router(solve.router)


@app.get("/api/config")
def config():
    return {"auth_enabled": auth_enabled()}


@app.get("/api/health")
def health():
    return JSONResponse({"status": "ok"})


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


# Frontend estático (CSS/JS).
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
