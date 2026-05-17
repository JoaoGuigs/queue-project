"""Tests for ``POST /reports/queue-activity/export`` CSV streaming."""

from __future__ import annotations

from typing import Any, AsyncIterator

import pytest

from tests.test_reports import API_KEY, HEADERS


async def _fake_csv_stream(
    pool: object,
    request: object,
) -> AsyncIterator[bytes]:
    _ = pool, request
    yield "\ufeff".encode("utf-8")
    yield "Data/Hora,Fila,Agente ID\n".encode("utf-8")
    yield "2026-05-12 10:00:00,sales,1001\n".encode("utf-8")


@pytest.fixture
def export_client(monkeypatch: pytest.MonkeyPatch, client: Any) -> Any:
    # Patch no router: o import em reports.py já fixou a referência ao importar.
    monkeypatch.setattr(
        "app.routers.reports.stream_queuemon_csv",
        _fake_csv_stream,
    )
    return client


def test_export_csv_returns_attachment(export_client: Any) -> None:
    body = {"period_type": "weekly", "year": 2026, "week": 20}
    r = export_client.post("/reports/queue-activity/export", json=body, headers=HEADERS)
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    assert "attachment" in r.headers.get("content-disposition", "")
    assert "queue-activity-2026-W20" in r.headers.get("content-disposition", "")

    text = r.content.decode("utf-8-sig")
    assert "Data/Hora,Fila,Agente ID" in text
    assert "sales,1001" in text


def test_export_csv_missing_api_key(client: Any) -> None:
    body = {"period_type": "weekly", "year": 2026, "week": 20}
    r = client.post("/reports/queue-activity/export", json=body)
    assert r.status_code == 403


def test_export_filename_monthly(export_client: Any) -> None:
    body = {"period_type": "monthly", "year": 2026, "month": 5}
    r = export_client.post("/reports/queue-activity/export", json=body, headers=HEADERS)
    assert r.status_code == 200
    assert "queue-activity-2026-05" in r.headers.get("content-disposition", "")
