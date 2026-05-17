"""Stream detailed PBX_QUEUEMON rows as CSV (memory-safe for large exports)."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Any, AsyncIterator, Sequence

import aiomysql

from app.database import iter_dict_rows
from app.schemas.request import PeriodType, QueueActivityRequest
from app.services.queue_report import _queue_agent_filter_clauses, resolve_period

# Colunas do CSV (chave no dict da query → cabeçalho no arquivo)
CSV_COLUMNS: tuple[tuple[str, str], ...] = (
    ("calldate", "Data/Hora"),
    ("queue", "Fila"),
    ("member", "Agente ID"),
    ("agent_name", "Agente Nome"),
    ("answered", "Atendida"),
    ("callerabandon", "Abandonada"),
    ("calltransfer", "Transferida"),
    ("callforward", "Encaminhada"),
    ("talk_time", "Talk (s)"),
    ("duration", "Duracao (s)"),
    ("linkedid", "LinkedID"),
)

FETCH_BATCH_SIZE = 1000
CSV_YIELD_EVERY = 500


def build_export_filename(request: QueueActivityRequest, period_start: date, period_end: date) -> str:
    """Human-readable attachment name for the download."""
    if request.period_type == PeriodType.weekly:
        assert request.week is not None
        label = f"{request.year}-W{request.week:02d}"
    else:
        assert request.month is not None
        label = f"{request.year}-{request.month:02d}"
    return f"queue-activity-{label}-{period_start.isoformat()}-{period_end.isoformat()}.csv"


def _detail_sql(filter_sql: str) -> str:
    return f"""
        SELECT
            q.calldate,
            q.queue,
            q.member,
            COALESCE(a.agent_name, '') AS agent_name,
            q.answered,
            q.callerabandon,
            COALESCE(q.calltransfer, 0) AS calltransfer,
            COALESCE(q.callforward, 0) AS callforward,
            q.talk_time,
            q.duration,
            q.linkedid
        FROM PBX_QUEUEMON q
        LEFT JOIN PBX_AGENT a ON q.member = a.agent_id
        WHERE q.calldate >= %s AND q.calldate < %s
        {filter_sql}
        ORDER BY q.calldate, q.queue, q.member
    """


def _format_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def _row_to_csv_values(row: dict[str, Any]) -> list[str]:
    return [_format_cell(row.get(key)) for key, _ in CSV_COLUMNS]

# retorna cada linha do csv como um dict
async def iter_queuemon_detail_rows(
    pool: aiomysql.Pool,
    start: datetime,
    end: datetime,
    filter_sql: str,
    filter_params: Sequence[Any],
) -> AsyncIterator[dict[str, Any]]:
    """One dict per PBX_QUEUEMON row (no GROUP BY)."""
    sql = _detail_sql(filter_sql)
    async for row in iter_dict_rows(
        pool,
        sql,
        (start, end, *filter_params),
        batch_size=FETCH_BATCH_SIZE,
    ):
        yield row


async def stream_queuemon_csv(
    pool: aiomysql.Pool,
    request: QueueActivityRequest,
) -> AsyncIterator[bytes]:
    """
    Async generator consumed by FastAPI ``StreamingResponse``.

    Yields UTF-8 chunks (with BOM) instead of building one giant string in memory.
    """
    start, end, _, _ = resolve_period(request)
    filter_sql, filter_params = _queue_agent_filter_clauses(request.queues, request.agents)

    yield "\ufeff".encode("utf-8")

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([label for _, label in CSV_COLUMNS])
    yield buffer.getvalue().encode("utf-8")
    buffer.seek(0)
    buffer.truncate(0)

    pending_rows = 0
    async for row in iter_queuemon_detail_rows(pool, start, end, filter_sql, filter_params):
        writer.writerow(_row_to_csv_values(row))
        pending_rows += 1
        if pending_rows >= CSV_YIELD_EVERY:
            yield buffer.getvalue().encode("utf-8")
            buffer.seek(0)
            buffer.truncate(0)
            pending_rows = 0

    if buffer.tell() > 0:
        yield buffer.getvalue().encode("utf-8")
