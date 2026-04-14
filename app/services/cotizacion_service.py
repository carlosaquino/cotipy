import asyncio
import logging
from datetime import datetime, timezone

import httpx

from app.core.cache import RateCache
from app.core.config import settings
from app.models.schemas import SourceName, SourceResult

logger = logging.getLogger(__name__)


class CotizacionService:
    """Orquesta el scraping, cache y recuperación de cotizaciones."""

    def __init__(self, cache: RateCache, client: httpx.AsyncClient) -> None:
        self._cache = cache
        self._client = client

    def _get_active_sources(self) -> list[SourceName]:
        active = []
        if settings.ENABLE_BCP:
            active.append(SourceName.BCP)
        if settings.ENABLE_MAXICAMBIOS:
            active.append(SourceName.MAXICAMBIOS)
        if settings.ENABLE_CAMBIOS_CHACO:
            active.append(SourceName.CAMBIOS_CHACO)
        return active

    def _make_scraper(self, source: SourceName):
        if source == SourceName.BCP:
            from app.scrapers.bcp import BCPScraper
            return BCPScraper()
        if source == SourceName.CAMBIOS_CHACO:
            from app.scrapers.cambios_chaco import CambiosChacoScraper
            return CambiosChacoScraper()
        if source == SourceName.MAXICAMBIOS:
            from app.scrapers.maxicambios import MaxicambiosScraper
            return MaxicambiosScraper()
        raise ValueError(f"Fuente desconocida: {source}")

    async def _fetch_source(self, source: SourceName) -> SourceResult:
        cached = self._cache.get(source)
        if cached is not None:
            logger.debug("Cache hit para fuente '%s'", source.value)
            return cached

        logger.info("Cache miss para fuente '%s', scrapeando…", source.value)
        try:
            scraper = self._make_scraper(source)
            result = await scraper.fetch_and_parse(self._client)
            await self._cache.set(source, result)
            return result
        except Exception as exc:
            logger.warning("Error scrapeando '%s': %s", source.value, exc)
            stale = self._cache.get_stale(source)
            if stale is not None:
                logger.info("Retornando cache desactualizado para '%s'", source.value)
                return stale
            return SourceResult(
                fuente=source,
                cotizaciones=[],
                actualizado_en=datetime.now(timezone.utc),
                desactualizado=False,
                error=str(exc),
            )

    async def get_all_rates(self) -> list[SourceResult]:
        active = self._get_active_sources()
        if not active:
            return []
        results = await asyncio.gather(*[self._fetch_source(s) for s in active])
        return list(results)

    async def get_source_rates(self, source: SourceName) -> SourceResult:
        flag_map = {
            SourceName.BCP: settings.ENABLE_BCP,
            SourceName.MAXICAMBIOS: settings.ENABLE_MAXICAMBIOS,
            SourceName.CAMBIOS_CHACO: settings.ENABLE_CAMBIOS_CHACO,
        }
        if not flag_map.get(source, True):
            return SourceResult(
                fuente=source,
                cotizaciones=[],
                actualizado_en=datetime.now(timezone.utc),
                error="fuente deshabilitada",
            )
        return await self._fetch_source(source)

    async def health_check(self) -> dict[str, str]:
        source_flags = {
            SourceName.BCP: settings.ENABLE_BCP,
            SourceName.MAXICAMBIOS: settings.ENABLE_MAXICAMBIOS,
            SourceName.CAMBIOS_CHACO: settings.ENABLE_CAMBIOS_CHACO,
        }
        status: dict[str, str] = {}
        for source, enabled in source_flags.items():
            if not enabled:
                status[source.value] = "deshabilitado"
            elif self._cache.get(source) is not None:
                status[source.value] = "ok"
            elif self._cache.get_stale(source) is not None:
                status[source.value] = "desactualizado"
            else:
                status[source.value] = "error"
        return status
