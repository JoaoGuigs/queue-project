"""Build queue activity reports from PBX_QUEUEMON (+ PBX_AGENT, optional cdr)."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Sequence

import aiomysql

from app.database import fetch_all, fetch_one
from app.schemas.request import PeriodType, QueueActivityRequest
from app.schemas.response import (
    AgentMetrics,
    DayMetrics,
    QueueActivityResponse,
    QueueMetrics,
    Summary,
)


@lru_cache(maxsize=128)
def iso_week_date_range(year: int, week: int) -> tuple[date, date]:
    """Pure helper: ISO Monday through Sunday for ``(year, week)``."""
    start = date.fromisocalendar(year, week, 1)  # Segunda da semana ISO
    end = start + timedelta(days=6)  # Domingo da mesma semana
    return start, end


def resolve_period(request: QueueActivityRequest) -> tuple[datetime, datetime, date, date]:
    """Return (start_dt inclusive, end_dt exclusive, period_start, period_end inclusive dates)."""
    if request.period_type == PeriodType.weekly:
        assert request.week is not None
        period_start, period_end = iso_week_date_range(request.year, request.week)
    else:
        assert request.month is not None
        period_start = date(request.year, request.month, 1)  # Primeiro dia do mês
        if request.month == 12:
            next_month_first = date(request.year + 1, 1, 1)
        else:
            next_month_first = date(request.year, request.month + 1, 1)
        period_end = next_month_first - timedelta(days=1)  # Último dia do mês

    start_dt = datetime.combine(period_start, datetime.min.time())  # Início do dia (00:00)
    if request.period_type == PeriodType.weekly:
        end_dt = datetime.combine(period_end + timedelta(days=1), datetime.min.time())  # Exclusivo: 00:00 do dia seguinte ao domingo
    else:
        assert request.month is not None
        if request.month == 12:
            end_dt = datetime(request.year + 1, 1, 1)  # Exclusivo: 1º jan do ano seguinte
        else:
            end_dt = datetime(request.year, request.month + 1, 1)  # Exclusivo: 1º dia do mês seguinte

    return start_dt, end_dt, period_start, period_end


def _queue_agent_filter_clauses(
    queues: list[str] | None,
    agents: list[str] | None,
) -> tuple[str, list[Any]]:
    """Build extra SQL AND fragments and positional parameters."""
    clauses: list[str] = []
    params: list[Any] = []
    if queues:
        placeholders = ",".join(["%s"] * len(queues))
        clauses.append(f"q.queue IN ({placeholders})")  # Filtro opcional por nome de fila
        params.extend(queues)
    if agents:
        placeholders = ",".join(["%s"] * len(agents))
        clauses.append(f"q.member IN ({placeholders})")  # member costuma ser o ramal / agent_id
        params.extend(agents)
    extra = ""
    if clauses:
        extra = " AND " + " AND ".join(clauses)
    return extra, params


async def _fetch_summary(
    pool: aiomysql.Pool,
    start: datetime,
    end: datetime,
    filter_sql: str,
    filter_params: Sequence[Any],
) -> dict[str, Any]:
    sql = f"""
        SELECT
            COUNT(*) AS total_calls,
            COALESCE(SUM(q.answered = 1), 0) AS answered,
            COALESCE(SUM(q.callerabandon = 1), 0) AS abandoned,
            COALESCE(SUM(COALESCE(q.calltransfer, 0) <> 0), 0) AS transferred,
            COALESCE(SUM(COALESCE(q.callforward, 0) <> 0), 0) AS forwarded,
            COALESCE(AVG(NULLIF(q.talk_time, NULL)), 0) AS avg_talk_time,
            COALESCE(AVG(q.duration), 0) AS avg_duration
        FROM PBX_QUEUEMON q
        LEFT JOIN PBX_AGENT a ON q.member = a.agent_id  # Nome do agente (quando existir cadastro)
        WHERE q.calldate >= %s AND q.calldate < %s  # Janela [start, end) em calldate
        {filter_sql}
    """
    row = await fetch_one(pool, sql, (start, end, *filter_params))
    return dict(row or {})


async def _fetch_cdr_orphans(
    pool: aiomysql.Pool,
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    """Distinct linkedids present in cdr in the window but absent from PBX_QUEUEMON in same window."""
    sql = """
        SELECT COUNT(DISTINCT c.linkedid) AS cdr_linkedids_not_in_queuemon
        FROM cdr c
        WHERE c.calldate >= %s AND c.calldate < %s
          AND c.linkedid IS NOT NULL
          AND TRIM(c.linkedid) <> ''
          AND NOT EXISTS (
              SELECT 1
              FROM PBX_QUEUEMON q
              WHERE q.linkedid = c.linkedid
                AND q.calldate >= %s AND q.calldate < %s
          )
    """  # CDR orfao: linkedid sem PBX_QUEUEMON no mesmo intervalo de tempo
    row = await fetch_one(pool, sql, (start, end, start, end))
    return dict(row or {"cdr_linkedids_not_in_queuemon": 0})


async def _fetch_by_queue(
    pool: aiomysql.Pool,
    start: datetime,
    end: datetime,
    filter_sql: str,
    filter_params: Sequence[Any],
) -> list[dict[str, Any]]:
    # Quebra por fila (coluna queue)
    sql = f"""
        SELECT
            q.queue AS queue,
            COUNT(*) AS total_calls,
            COALESCE(SUM(q.answered = 1), 0) AS answered,
            COALESCE(SUM(q.callerabandon = 1), 0) AS abandoned,
            COALESCE(AVG(NULLIF(q.talk_time, NULL)), 0) AS avg_talk_time
        FROM PBX_QUEUEMON q
        LEFT JOIN PBX_AGENT a ON q.member = a.agent_id
        WHERE q.calldate >= %s AND q.calldate < %s
        {filter_sql}
        GROUP BY q.queue
        ORDER BY total_calls DESC
    """
    return await fetch_all(pool, sql, (start, end, *filter_params))


async def _fetch_by_agent(
    pool: aiomysql.Pool,
    start: datetime,
    end: datetime,
    filter_sql: str,
    filter_params: Sequence[Any],
) -> list[dict[str, Any]]:
    # Agrega por agente (member ↔ agent_id)
    sql = f"""
        SELECT
            COALESCE(a.agent_id, q.member) AS agent_id,
            COALESCE(a.agent_name, '') AS agent_name,
            COALESCE(SUM(q.answered = 1), 0) AS answered,
            COALESCE(AVG(NULLIF(q.talk_time, NULL)), 0) AS avg_talk_time
        FROM PBX_QUEUEMON q
        LEFT JOIN PBX_AGENT a ON q.member = a.agent_id
        WHERE q.calldate >= %s AND q.calldate < %s
        {filter_sql}
        GROUP BY COALESCE(a.agent_id, q.member), COALESCE(a.agent_name, '')
        ORDER BY answered DESC
    """
    return await fetch_all(pool, sql, (start, end, *filter_params))


async def _fetch_by_day(
    pool: aiomysql.Pool,
    start: datetime,
    end: datetime,
    filter_sql: str,
    filter_params: Sequence[Any],
) -> list[dict[str, Any]]:
    # Série diária (DATE(calldate))
    sql = f"""
        SELECT
            DATE(q.calldate) AS d,
            COUNT(*) AS total_calls,
            COALESCE(SUM(q.answered = 1), 0) AS answered,
            COALESCE(SUM(q.callerabandon = 1), 0) AS abandoned
        FROM PBX_QUEUEMON q
        LEFT JOIN PBX_AGENT a ON q.member = a.agent_id
        WHERE q.calldate >= %s AND q.calldate < %s
        {filter_sql}
        GROUP BY DATE(q.calldate)
        ORDER BY d
    """
    return await fetch_all(pool, sql, (start, end, *filter_params))


async def gather_report_sections(
    pool: aiomysql.Pool,
    request: QueueActivityRequest,
    start: datetime,
    end: datetime,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Run independent SQL slices concurrently. Exposed for tests via ``monkeypatch``."""
    filter_sql, filter_params = _queue_agent_filter_clauses(request.queues, request.agents)
    summary, by_queue, by_agent, by_day, cdr = await asyncio.gather(  # Consultas independentes em paralelo
        _fetch_summary(pool, start, end, filter_sql, filter_params),
        _fetch_by_queue(pool, start, end, filter_sql, filter_params),
        _fetch_by_agent(pool, start, end, filter_sql, filter_params),
        _fetch_by_day(pool, start, end, filter_sql, filter_params),
        _fetch_cdr_orphans(pool, start, end),
    )
    return summary, by_queue, by_agent, by_day, cdr


def _answer_rate_pct(answered: int, total: int) -> float:
    if total <= 0:
        return 0.0  # Evita divisão por zero
    return round(100.0 * answered / total, 2)


def _to_summary(
    summary: dict[str, Any],
    cdr: dict[str, Any],
) -> Summary:
    total = int(summary.get("total_calls") or 0)
    answered = int(summary.get("answered") or 0)
    return Summary(  # Une totais da fila + métrica extra do CDR
        total_calls=total,
        answered=answered,
        abandoned=int(summary.get("abandoned") or 0),
        transferred=int(summary.get("transferred") or 0),
        forwarded=int(summary.get("forwarded") or 0),
        avg_talk_time_sec=float(summary.get("avg_talk_time") or 0),
        avg_duration_sec=float(summary.get("avg_duration") or 0),
        answer_rate_pct=_answer_rate_pct(answered, total),
        cdr_linkedids_not_in_queuemon=int(cdr.get("cdr_linkedids_not_in_queuemon") or 0),
    )


async def build_queue_activity_report(
    pool: aiomysql.Pool,
    request: QueueActivityRequest,
) -> QueueActivityResponse:
    """Main entry: aggregate PBX_QUEUEMON (+ PBX_AGENT, cdr orphan metric) for the requested window."""
    start, end, period_start, period_end = resolve_period(request)  # Converte body → intervalo SQL
    summary, by_queue, by_agent, by_day, cdr = await gather_report_sections(
        pool, request, start, end
    )

    return QueueActivityResponse(
        period_type=request.period_type.value,
        period_start=period_start,
        period_end=period_end,
        generated_at=datetime.now(timezone.utc),
        cached=False,
        summary=_to_summary(summary, cdr),
        by_queue=[
            QueueMetrics(
                queue=str(r["queue"]),
                total_calls=int(r["total_calls"]),
                answered=int(r["answered"]),
                abandoned=int(r["abandoned"]),
                avg_talk_time_sec=float(r["avg_talk_time"] or 0),
            )
            for r in by_queue
        ],
        by_agent=[
            AgentMetrics(
                agent_id=str(r["agent_id"]),
                agent_name=str(r["agent_name"]),
                answered=int(r["answered"]),
                avg_talk_time_sec=float(r["avg_talk_time"] or 0),
            )
            for r in by_agent
        ],
        by_day=[
            DayMetrics(
                date=r["d"] if isinstance(r["d"], date) else r["d"].date(),  # MySQL pode devolver date ou datetime
                total_calls=int(r["total_calls"]),
                answered=int(r["answered"]),
                abandoned=int(r["abandoned"]),
            )
            for r in by_day
        ],
    )
