import asyncio
import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import router as api_v1_router
from app.core.cache import RateCache
from app.core.config import settings
from app.core.database import engine
from app.models.db_models import Base
from app.models.schemas import HealthResponse
from app.services.cotizacion_service import CotizacionService
from app.services.history_service import HistoryService

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


async def _refresh_loop(
    service: CotizacionService,
    history_service: HistoryService,
    interval: int,
) -> None:
    logger.info("Loop de refresco iniciado (intervalo=%ds)", interval)
    while True:
        await asyncio.sleep(interval)
        try:
            results = await service.get_all_rates()
            all_rates = [rate for result in results for rate in result.cotizaciones]
            if all_rates:
                await history_service.save_rates(all_rates)
                logger.info("Refresco automático: %d cotizaciones guardadas", len(all_rates))
        except Exception as exc:
            logger.warning("Error en refresco automático: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("data", exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Tablas de base de datos verificadas")

    client = httpx.AsyncClient(
        headers={"User-Agent": settings.USER_AGENT},
        follow_redirects=True,
    )

    cache = RateCache()
    service = CotizacionService(cache=cache, client=client)
    history_service = HistoryService()

    app.state.service = service
    app.state.history_service = history_service

    refresh_task: asyncio.Task | None = None
    if settings.REFRESH_INTERVAL_SECONDS > 0:
        refresh_task = asyncio.create_task(
            _refresh_loop(service, history_service, settings.REFRESH_INTERVAL_SECONDS)
        )

    logger.info("%s %s iniciado", settings.APP_NAME, settings.APP_VERSION)
    yield

    if refresh_task is not None:
        refresh_task.cancel()
        try:
            await refresh_task
        except asyncio.CancelledError:
            pass

    await client.aclose()
    logger.info("%s apagado", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router)

app.mount("/recursos", StaticFiles(directory="recursos"), name="recursos")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def docs_web() -> HTMLResponse:
    """Página de documentación web."""
    with open("app/static/index.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/health", response_model=HealthResponse, tags=["sistema"])
async def health() -> HealthResponse:
    """Estado de salud de la aplicación."""
    service: CotizacionService = app.state.service
    fuentes_status = await service.health_check()

    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:
        logger.warning("Error en health check de DB: %s", exc)
        db_status = "error"

    return HealthResponse(
        estado="ok" if db_status == "ok" else "degradado",
        version=settings.APP_VERSION,
        fuentes=fuentes_status,
        base_de_datos=db_status,
    )
