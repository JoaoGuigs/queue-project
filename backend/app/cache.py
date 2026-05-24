"""Distributed cache for assembled report payloads using Redis.

Stores payloads as JSON strings with a 10-second TTL.
Unlike the in-memory cache, this is shared across all Uvicorn workers
and scales horizontally.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import redis.asyncio as redis

from app.config import settings
from app.schemas.request import QueueActivityRequest

# Cria a conexão com o Redis. 
# decode_responses=True garante que o Redis devolva strings em vez de bytes.
redis_client = redis.from_url(settings.redis_url, decode_responses=True)


def make_cache_key(request: QueueActivityRequest) -> str:
    """Stable hash key from the normalized JSON representation."""
    data = request.model_dump(mode="json")  # Tipos JSON-safe (ex.: date → string)
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)  # Chave estável
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def get_cached_report(cache_key: str) -> Any | None:
    """Fetches the report from Redis and parses the JSON back to a dictionary."""
    cached_data = await redis_client.get(cache_key)
    
    if cached_data is not None:
        # Transforma o texto JSON do Redis de volta em um dicionário Python
        return json.loads(cached_data)
        
    return None


async def set_cached_report(cache_key: str, value: Any) -> None:
    """Serializes the payload to JSON and stores it in Redis with a 10s TTL."""
    # Transforma o dicionário (value) em texto JSON puro
    json_data = json.dumps(value)
    
    # setex = Set with Expiration (Chave, Tempo em Segundos, Valor)
    await redis_client.setex(name=cache_key, time=10, value=json_data)