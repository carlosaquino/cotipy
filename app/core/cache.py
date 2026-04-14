import asyncio
import logging
from datetime import datetime, timezone

from app.core.config import settings
from app.models.schemas import SourceName, SourceResult

logger = logging.getLogger(__name__)


class RateCache:
    """In-memory cache for SourceResult objects with TTL expiration."""

    def __init__(self) -> None:
        self._store: dict[SourceName, SourceResult] = {}
        self._timestamps: dict[SourceName, datetime] = {}
        self._lock = asyncio.Lock()

    def _is_expired(self, source: SourceName) -> bool:
        ts = self._timestamps.get(source)
        if ts is None:
            return True
        elapsed = (datetime.now(timezone.utc) - ts).total_seconds()
        return elapsed > settings.CACHE_TTL_SECONDS

    def get(self, source: SourceName) -> SourceResult | None:
        """Return cached SourceResult if it exists and has not expired, else None."""
        if source not in self._store:
            return None
        if self._is_expired(source):
            logger.debug("Cache expired for source '%s'", source.value)
            return None
        return self._store[source]

    def get_stale(self, source: SourceName) -> SourceResult | None:
        """Return cached SourceResult regardless of TTL, marked as stale."""
        result = self._store.get(source)
        if result is None:
            return None
        if self._is_expired(source):
            stale = result.model_copy(update={"is_stale": True})
            logger.debug("Returning stale cache for source '%s'", source.value)
            return stale
        return result

    async def set(self, source: SourceName, result: SourceResult) -> None:
        """Store a SourceResult in the cache with the current timestamp."""
        async with self._lock:
            self._store[source] = result
            self._timestamps[source] = datetime.now(timezone.utc)
            logger.debug("Cache updated for source '%s'", source.value)

    def get_all_sources(self) -> list[SourceName]:
        """Return list of sources that currently have cached data."""
        return list(self._store.keys())
