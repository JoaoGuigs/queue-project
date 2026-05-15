"""Queue activity report HTTP routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks

from app.cache import get_cached_report, make_cache_key, set_cached_report
from app.dependencies import ApiKeyDep, DbPoolDep
from app.schemas.request import QueueActivityRequest
from app.schemas.response import QueueActivityResponse
from app.services.queue_report import build_queue_activity_report

router = APIRouter(prefix="/reports", tags=["reports"])  # Agrupa rotas sob /reports
logger = logging.getLogger(__name__)


def _log_report_finished(cache_key_prefix: str, period_type: str) -> None:
    """Lightweight post-response logging (safe for ``BackgroundTasks``)."""
    logger.info("queue-activity report done period=%s key=%s", period_type, cache_key_prefix)


@router.post(
    "/queue-activity",
    response_model=QueueActivityResponse,
    summary="Queue activity report",
    description=(
        "Returns aggregated queue metrics for a **weekly** or **monthly** window "
        "from ``PBX_QUEUEMON`` joined to ``PBX_AGENT``. Includes a **cdr** orphan "
        "metric (distinct ``linkedid`` in ``cdr`` without a matching row in "
        "``PBX_QUEUEMON`` in the same window). Requires header ``X-API-Key``."
    ),
)
async def queue_activity_report(
    body: QueueActivityRequest,
    background_tasks: BackgroundTasks,
    _api_key: ApiKeyDep,
    pool: DbPoolDep,
) -> QueueActivityResponse:
    _ = _api_key  # Só força validação da dependency (valor não usado aqui)
    cache_key = make_cache_key(body)
    cached = await get_cached_report(cache_key)
    if cached is not None:
        model = QueueActivityResponse.model_validate(cached)  # Reidrata Pydantic a partir do dict cacheado
        return model.model_copy(update={"cached": True})  # Indica ao cliente que veio do cache

    report = await build_queue_activity_report(pool, body)  # Agregação SQL + montagem da resposta
    payload = report.model_dump(mode="json")  # Formato estável para guardar no TTLCache
    await set_cached_report(cache_key, payload)

    background_tasks.add_task(_log_report_finished, cache_key[:16], body.period_type.value)  # Log leve após enviar resposta

    return report
