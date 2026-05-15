"""Pydantic models for queue activity report JSON responses."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class Summary(BaseModel):
    """Aggregate metrics for the whole period (PBX_QUEUEMON + optional cdr signal)."""

    total_calls: int = Field(..., ge=0)  # Linhas PBX_QUEUEMON no período (após filtros)
    answered: int = Field(..., ge=0)  # answered = 1
    abandoned: int = Field(..., ge=0)  # callerabandon = 1
    transferred: int = Field(..., ge=0)  # calltransfer != 0
    forwarded: int = Field(..., ge=0)  # callforward != 0
    avg_talk_time_sec: float = Field(..., ge=0)  # Média de talk_time (NULL ignorado)
    avg_duration_sec: float = Field(..., ge=0)  # Média de duration
    answer_rate_pct: float = Field(..., ge=0, le=100)  # answered / total_calls * 100
    cdr_linkedids_not_in_queuemon: int = Field(
        default=0,
        ge=0,
        description=(
            "Count of distinct cdr.linkedid in the period that have no matching "
            "PBX_QUEUEMON row with the same linkedid in the same period."
        ),
    )  # Sinal de chamadas só no CDR (sem linha correspondente na fila no intervalo)


class QueueMetrics(BaseModel):
    """Per-queue slice."""

    queue: str
    total_calls: int = Field(..., ge=0)
    answered: int = Field(..., ge=0)
    abandoned: int = Field(..., ge=0)
    avg_talk_time_sec: float = Field(..., ge=0)


class AgentMetrics(BaseModel):
    """Per-agent slice (from PBX_QUEUEMON.member joined to PBX_AGENT)."""

    agent_id: str
    agent_name: str
    answered: int = Field(..., ge=0)
    avg_talk_time_sec: float = Field(..., ge=0)


class DayMetrics(BaseModel):
    """Per-calendar-day slice."""

    date: date
    total_calls: int = Field(..., ge=0)
    answered: int = Field(..., ge=0)
    abandoned: int = Field(..., ge=0)


class QueueActivityResponse(BaseModel):
    """Full report payload."""

    period_type: str
    period_start: date  # Primeiro dia inclusivo do relatório
    period_end: date  # Último dia inclusivo do relatório
    generated_at: datetime  # Momento UTC da montagem da resposta
    cached: bool  # True se veio do cache de 10s
    summary: Summary
    by_queue: list[QueueMetrics]
    by_agent: list[AgentMetrics]
    by_day: list[DayMetrics]
