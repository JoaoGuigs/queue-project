"""Tests for ``POST /reports/queue-activity``."""

from __future__ import annotations

import pytest


API_KEY = "pytest-api-key"  # Mesmo valor forçado em tests/conftest.py
HEADERS = {"X-API-Key": API_KEY}  # Header exigido pelo endpoint


def test_valid_weekly(client) -> None:
    body = {"period_type": "weekly", "year": 2026, "week": 20}
    r = client.post("/reports/queue-activity", json=body, headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["period_type"] == "weekly"
    assert data["period_start"] == "2026-05-11"
    assert data["period_end"] == "2026-05-17"
    assert data["cached"] is False
    assert data["summary"]["total_calls"] == 10
    assert data["summary"]["answered"] == 8
    assert data["summary"]["answer_rate_pct"] == 80.0
    assert data["summary"]["cdr_linkedids_not_in_queuemon"] == 1
    assert len(data["by_queue"]) == 1
    assert data["by_queue"][0]["queue"] == "sales"


def test_valid_monthly(client) -> None:
    body = {"period_type": "monthly", "year": 2026, "month": 5}
    r = client.post("/reports/queue-activity", json=body, headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["period_type"] == "monthly"
    assert data["period_start"] == "2026-05-01"
    assert data["period_end"] == "2026-05-31"


def test_invalid_body_missing_year(client) -> None:
    body = {"period_type": "weekly", "week": 10}
    r = client.post("/reports/queue-activity", json=body, headers=HEADERS)
    assert r.status_code == 422


def test_inconsistent_period_weekly_without_week(client) -> None:
    body = {"period_type": "weekly", "year": 2026}
    r = client.post("/reports/queue-activity", json=body, headers=HEADERS)
    assert r.status_code == 422


def test_inconsistent_period_weekly_with_month(client) -> None:
    body = {"period_type": "weekly", "year": 2026, "week": 5, "month": 3}
    r = client.post("/reports/queue-activity", json=body, headers=HEADERS)
    assert r.status_code == 422


def test_missing_api_key(client) -> None:
    body = {"period_type": "weekly", "year": 2026, "week": 20}
    r = client.post("/reports/queue-activity", json=body)
    assert r.status_code == 403


def test_wrong_api_key(client) -> None:
    body = {"period_type": "weekly", "year": 2026, "week": 20}
    r = client.post(
        "/reports/queue-activity",
        json=body,
        headers={"X-API-Key": "wrong"},
    )
    assert r.status_code == 403


def test_cache_hit_sets_cached_flag(client, monkeypatch: pytest.MonkeyPatch) -> None:
    """Segunda request igual deve bater no cache (10s) e não reexecutar o gather."""
    calls: list[int] = []

    async def counting_gather(*args: object, **kwargs: object):
        calls.append(1)
        from datetime import date as d  # noqa: PLC0415

        return (
            {
                "total_calls": 1,
                "answered": 1,
                "abandoned": 0,
                "transferred": 0,
                "forwarded": 0,
                "avg_talk_time": 1.0,
                "avg_duration": 1.0,
            },
            [{"queue": "q", "total_calls": 1, "answered": 1, "abandoned": 0, "avg_talk_time": 1.0}],
            [{"agent_id": "a", "agent_name": "n", "answered": 1, "avg_talk_time": 1.0}],
            [{"d": d(2026, 1, 1), "total_calls": 1, "answered": 1, "abandoned": 0}],
            {"cdr_linkedids_not_in_queuemon": 0},
        )

    monkeypatch.setattr(
        "app.services.queue_report.gather_report_sections",
        counting_gather,
    )

    body = {"period_type": "monthly", "year": 2026, "month": 1}
    r1 = client.post("/reports/queue-activity", json=body, headers=HEADERS)
    r2 = client.post("/reports/queue-activity", json=body, headers=HEADERS)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["cached"] is False
    assert r2.json()["cached"] is True
    assert len(calls) == 1
