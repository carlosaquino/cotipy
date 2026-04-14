import logging
from datetime import date

from fastapi import APIRouter, Depends, Query, Request

from app.models.schemas import (
    DailyAverageResponse,
    HistoryResponse,
    SourceName,
)
from app.services.history_service import HistoryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/historial", tags=["historial"])


def get_history_service(request: Request) -> HistoryService:
    return request.app.state.history_service


@router.get("/{moneda}", response_model=HistoryResponse)
async def get_historial(
    moneda: str,
    fuente: SourceName | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    sucursal: str | None = None,
    limite: int = Query(default=100, ge=1, le=500),
    history_service: HistoryService = Depends(get_history_service),
) -> HistoryResponse:
    """Retorna el historial de cotizaciones para una moneda."""
    return await history_service.get_history(
        currency_code=moneda,
        source=fuente,
        date_from=fecha_desde,
        date_to=fecha_hasta,
        location=sucursal,
        limit=limite,
    )


@router.get("/{moneda}/diario", response_model=DailyAverageResponse)
async def get_promedios_diarios(
    moneda: str,
    fuente: SourceName | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    history_service: HistoryService = Depends(get_history_service),
) -> DailyAverageResponse:
    """Retorna los promedios diarios de compra/venta/referencial para una moneda."""
    return await history_service.get_daily_averages(
        currency_code=moneda,
        source=fuente,
        date_from=fecha_desde,
        date_to=fecha_hasta,
    )
