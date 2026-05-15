"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import close_pool, create_pool
from app.http_client import create_async_client
from app.routers import reports

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: DB pool + shared ``httpx`` client. Shutdown: cleanup."""
    pool = await create_pool()  # Pool MySQL (uma vez no startup)
    app.state.db_pool = pool  # Pool acessível via Depends(get_db_pool)
    app.state.http_client = create_async_client()  # Cliente HTTP assíncrono compartilhado
    logger.info("MySQL pool ready db=%s host=%s", settings.database_name, settings.database_host)

    # GET opcional no startup (EXTERNAL_STATUS_URL) — não bloqueia o servidor se falhar
    if settings.external_status_url:
        try:
            resp = await app.state.http_client.get(settings.external_status_url)
            logger.info("external_status_url probe status=%s", resp.status_code)
        except httpx.HTTPError as exc:
            logger.warning("external_status_url probe failed: %s", exc)

    yield  # Aplicação atendendo requests

    await app.state.http_client.aclose()  # Fecha conexões HTTP pendentes
    await close_pool(app.state.db_pool)  # Encerra pool MySQL
    logger.info("Shutdown complete")


app = FastAPI(
    title="Queue Activity Report API",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(reports.router)  # Rotas /reports/*


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    """Simple liveness probe (no DB check)."""
    return {"status": "ok"}  # Só indica que o processo está vivo


_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if _FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")
