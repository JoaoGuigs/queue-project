"""Pytest fixtures: env, fake DB pool, canned report SQL layer."""

from __future__ import annotations

import os
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient


# Variáveis de ambiente mínimas antes de importar ``app.config`` (evita erro de API_KEY ausente)
os.environ["API_KEY"] = "pytest-api-key"
os.environ.setdefault("DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("DATABASE_PORT", "3306")
os.environ.setdefault("DATABASE_USER", "pytest")
os.environ.setdefault("DATABASE_PASSWORD", "pytest")
os.environ.setdefault("DATABASE_NAME", "pytest")


class _DummyPool:
    """Pool falso: só satisfaz close/wait_closed do lifespan (sem MySQL real)."""

    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None


@pytest.fixture
def canned_gather_payload() -> tuple[dict[str, Any], list[dict], list[dict], list[dict], dict]:
    # Retorno no mesmo formato de ``gather_report_sections`` (5 tuplas)
    return (
        {
            "total_calls": 10,
            "answered": 8,
            "abandoned": 1,
            "transferred": 2,
            "forwarded": 0,
            "avg_talk_time": 45.5,
            "avg_duration": 120.0,
        },
        [
            {
                "queue": "sales",
                "total_calls": 10,
                "answered": 8,
                "abandoned": 1,
                "avg_talk_time": 45.5,
            }
        ],
        [
            {
                "agent_id": "1001",
                "agent_name": "Alice",
                "answered": 5,
                "avg_talk_time": 40.0,
            }
        ],
        [
            {
                "d": date(2026, 5, 12),
                "total_calls": 3,
                "answered": 2,
                "abandoned": 0,
            }
        ],
        {"cdr_linkedids_not_in_queuemon": 1},
    )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, canned_gather_payload: tuple) -> Any:
    async def _fake_create_pool() -> _DummyPool:
        return _DummyPool()

    async def _fake_gather(*_args: Any, **_kwargs: Any):
        return canned_gather_payload

    monkeypatch.setattr("app.database.create_pool", _fake_create_pool)  # Não abre conexão real
    monkeypatch.setattr(
        "app.services.queue_report.gather_report_sections",
        _fake_gather,  # Resposta determinística dos “SELECTs”
    )

    # Import após patches para o lifespan usar o pool fake
    from app.main import app as fastapi_app

    with TestClient(fastapi_app) as test_client:
        yield test_client
