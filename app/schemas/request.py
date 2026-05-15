"""Pydantic models for ``POST /reports/queue-activity`` request body."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class PeriodType(str, Enum):
    """Supported aggregation windows."""

    weekly = "weekly"  # Agregação por semana ISO (seg–dom)
    monthly = "monthly"  # Agregação por mês civil


class QueueActivityRequest(BaseModel):
    """JSON body for queue activity report generation."""

    period_type: PeriodType  # weekly ou monthly
    year: int = Field(..., ge=2000, le=2100)
    week: int | None = Field(default=None, ge=1, le=53)  # Obrigatório se weekly
    month: int | None = Field(default=None, ge=1, le=12)  # Obrigatório se monthly
    queues: list[str] | None = Field(
        default=None,
        description="If set, only these queue names are included.",
    )
    agents: list[str] | None = Field(
        default=None,
        description="If set, only rows whose PBX_AGENT.agent_id is in this list.",
    )

    @model_validator(mode="after")
    def check_period_fields(self) -> QueueActivityRequest:
        # Garante combinação coerente: semana XOR mês conforme period_type
        if self.period_type == PeriodType.weekly:
            if self.week is None:
                raise ValueError("week is required when period_type is weekly")
            if self.month is not None:
                raise ValueError("month must not be set when period_type is weekly")
        elif self.period_type == PeriodType.monthly:
            if self.month is None:
                raise ValueError("month is required when period_type is monthly")
            if self.week is not None:
                raise ValueError("week must not be set when period_type is monthly")
        return self
