"""Async MySQL pool and query helpers."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Sequence

import aiomysql

from app.config import settings


def _build_pool_kwargs() -> dict[str, Any]:
    # Parâmetros passados ao aiomysql.create_pool
    return {
        "host": settings.database_host,
        "port": settings.database_port,
        "user": settings.database_user,
        "password": settings.database_password,
        "db": settings.database_name,
        "autocommit": True,  # Evita transação implícita pendente em leituras
        "minsize": 1,
        "maxsize": 10,  # Limite de conexões simultâneas no pool
    }


async def create_pool() -> aiomysql.Pool:
    """Create a new connection pool (call once on startup)."""
    return await aiomysql.create_pool(**_build_pool_kwargs())


async def close_pool(pool: aiomysql.Pool | None) -> None:
    if pool is not None:
        pool.close()  # Para de aceitar novos acquire
        await pool.wait_closed()  # Espera conexões devolvidas fecharem


async def fetch_all(
    pool: aiomysql.Pool,
    sql: str,
    args: Sequence[Any] | None = None,
) -> list[dict[str, Any]]:
    """Execute SELECT and return all rows as dicts."""
    async with pool.acquire() as conn:  # Pega uma conexão do pool
        async with conn.cursor(aiomysql.DictCursor) as cur:  # Linhas como dict (chave = coluna)
            await cur.execute(sql, args or ())
            rows = await cur.fetchall()
            return list(rows)


async def fetch_one(
    pool: aiomysql.Pool,
    sql: str,
    args: Sequence[Any] | None = None,
) -> dict[str, Any] | None:
    """Execute SELECT and return first row or None."""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql, args or ())
            row = await cur.fetchone()  # Útil para SELECT com agregação (uma linha)
            return row

#itera sobre as linhas do resultado da query
#retorna cada linha como um dict
#batch_size é o tamanho do lote de linhas a serem retornadas
async def iter_dict_rows(
    pool: aiomysql.Pool,
    sql: str,
    args: Sequence[Any] | None = None,
    *,
    batch_size: int = 1000,
) -> AsyncIterator[dict[str, Any]]:
    """Stream SELECT rows in batches (keeps one connection open until exhausted)."""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql, args or ())
            while True:
                batch = await cur.fetchmany(batch_size)
                if not batch:
                    break
                for row in batch:
                    yield row


@asynccontextmanager
async def lifespan_pool() -> AsyncIterator[aiomysql.Pool]:
    """Context manager for tests or scripts needing a short-lived pool."""
    pool = await create_pool()
    try:
        yield pool
    finally:
        await close_pool(pool)
