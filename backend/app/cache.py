"""Short-lived in-memory cache for assembled report payloads.

Uses ``cachetools.TTLCache`` with a 10-second TTL.

**Limitation:** The cache is **per Python process**. If you run multiple
Uvicorn/Gunicorn workers, each worker maintains its own isolated cache.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

from cachetools import TTLCache

from app.schemas.request import QueueActivityRequest

# Cache em memória por processo: TTL 10s, até 256 chaves distintas
_report_cache: TTLCache[str, Any] = TTLCache(maxsize=256, ttl=10)
_cache_lock = asyncio.Lock()  # Evita corrida entre requests paralelos no mesmo worker


def make_cache_key(request: QueueActivityRequest) -> str:
    """Stable hash key from the normalized JSON representation."""
    data = request.model_dump(mode="json")  # Tipos JSON-safe (ex.: date → string)
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)  # Chave estável
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def get_cached_report(cache_key: str) -> Any | None:
    async with _cache_lock:
        return _report_cache.get(cache_key)  # Hit → dict serializado do relatório


async def set_cached_report(cache_key: str, value: Any) -> None:
    async with _cache_lock:
        _report_cache[cache_key] = value  # Armazena payload já em formato JSON-friendly
