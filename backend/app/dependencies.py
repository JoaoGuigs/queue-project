"""FastAPI dependencies (authentication, DB pool access)."""

from __future__ import annotations

from typing import Annotated

import aiomysql
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from app.config import settings

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)  # Lê o header sem 422 automático


async def verify_api_key(api_key: str | None = Security(API_KEY_HEADER)) -> str:
    """Validate ``X-API-Key`` header against configured ``API_KEY``."""
    if not api_key or api_key != settings.api_key:  # Comparação em texto puro (MVP)
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return api_key


def get_db_pool(request: Request) -> aiomysql.Pool:
    """Return the MySQL pool attached to app state."""
    pool = getattr(request.app.state, "db_pool", None)  # Definido no lifespan de main.py
    if pool is None:
        raise HTTPException(status_code=503, detail="Database pool not initialized")
    return pool


DbPoolDep = Annotated[aiomysql.Pool, Depends(get_db_pool)]  # Atalho de tipo + Depends
ApiKeyDep = Annotated[str, Depends(verify_api_key)]  # Garante API key antes do handler
