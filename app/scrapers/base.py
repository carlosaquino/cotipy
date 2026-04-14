import abc
from datetime import datetime, timezone

import httpx

from app.models.schemas import SourceName, SourceResult


class BaseScraper(abc.ABC):
    source: SourceName
    url: str
    timeout: float = 15.0

    @abc.abstractmethod
    async def parse(self, html: str) -> list:
        """Parse HTML and return a list of CurrencyRate objects."""
        ...

    async def fetch_and_parse(self, client: httpx.AsyncClient) -> SourceResult:
        response = await client.get(self.url, timeout=self.timeout)
        response.raise_for_status()
        rates = await self.parse(response.text)
        return SourceResult(
            fuente=self.source,
            cotizaciones=rates,
            actualizado_en=datetime.now(timezone.utc),
        )
