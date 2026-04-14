import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.models.schemas import (
    AllRatesResponse,
    CurrencyRate,
    RateType,
    SourceName,
    SourceResult,
)
from app.services.cotizacion_service import CotizacionService
from app.services.history_service import HistoryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cotizaciones", tags=["cotizaciones"])


def get_service(request: Request) -> CotizacionService:
    return request.app.state.service


def get_history_service(request: Request) -> HistoryService:
    return request.app.state.history_service


async def _save_rates_bg(history_service: HistoryService, rates: list[CurrencyRate]) -> None:
    try:
        await history_service.save_rates(rates)
    except Exception as exc:
        logger.warning("Error guardando en DB en background: %s", exc)


@router.get("", response_model=AllRatesResponse)
async def get_all_cotizaciones(
    background_tasks: BackgroundTasks,
    fuente: SourceName | None = None,
    tipo: RateType | None = None,
    sucursal: str | None = None,
    service: CotizacionService = Depends(get_service),
    history_service: HistoryService = Depends(get_history_service),
) -> AllRatesResponse:
    """Retorna las cotizaciones actuales de todas las fuentes (o de una fuente específica)."""
    if fuente is not None:
        results = [await service.get_source_rates(fuente)]
    else:
        results = await service.get_all_rates()

    all_rates_to_save: list[CurrencyRate] = []
    filtered_results: list[SourceResult] = []

    for result in results:
        if result.error is None:
            cots = result.cotizaciones
            if tipo is not None:
                cots = [r for r in cots if r.tipo == tipo]
            if sucursal is not None:
                cots = [r for r in cots if r.sucursal == sucursal]
            all_rates_to_save.extend(result.cotizaciones)
            filtered_results.append(result.model_copy(update={"cotizaciones": cots}))
        else:
            filtered_results.append(result)

    if all_rates_to_save:
        background_tasks.add_task(_save_rates_bg, history_service, all_rates_to_save)

    if all(r.error is not None for r in filtered_results) and filtered_results:
        raise HTTPException(status_code=503, detail="Todas las fuentes no están disponibles")

    return AllRatesResponse(
        fuentes=filtered_results,
        actualizado_en=datetime.now(timezone.utc),
    )


@router.get("/sources/{fuente}", response_model=SourceResult)
async def get_source_cotizaciones(
    fuente: SourceName,
    background_tasks: BackgroundTasks,
    service: CotizacionService = Depends(get_service),
    history_service: HistoryService = Depends(get_history_service),
) -> SourceResult:
    """Retorna las cotizaciones actuales de una fuente específica."""
    result = await service.get_source_rates(fuente)
    if result.error is None and result.cotizaciones:
        background_tasks.add_task(_save_rates_bg, history_service, result.cotizaciones)
    return result


@router.get("/{moneda}", response_model=AllRatesResponse)
async def get_currency_cotizaciones(
    moneda: str,
    background_tasks: BackgroundTasks,
    service: CotizacionService = Depends(get_service),
    history_service: HistoryService = Depends(get_history_service),
) -> AllRatesResponse:
    """Retorna las cotizaciones de una moneda específica en todas las fuentes."""
    results = await service.get_all_rates()
    code_upper = moneda.upper()
    all_rates_to_save: list[CurrencyRate] = []
    filtered_results: list[SourceResult] = []

    for result in results:
        if result.error is None:
            cots = [r for r in result.cotizaciones if r.moneda == code_upper]
            all_rates_to_save.extend(result.cotizaciones)
            filtered_results.append(result.model_copy(update={"cotizaciones": cots}))
        else:
            filtered_results.append(result)

    if all_rates_to_save:
        background_tasks.add_task(_save_rates_bg, history_service, all_rates_to_save)

    return AllRatesResponse(
        fuentes=filtered_results,
        actualizado_en=datetime.now(timezone.utc),
    )
