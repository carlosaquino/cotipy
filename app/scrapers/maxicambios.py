import asyncio
import json
import logging
import re
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup, Tag

from app.core.config import settings
from app.models.schemas import CurrencyRate, RateType, SourceName, SourceResult
from app.scrapers.base import BaseScraper
from app.scrapers.utils import parse_number

logger = logging.getLogger(__name__)

_FLAG_RE = re.compile(r"/([A-Z]{3})\.(?:png|jpg|svg|webp)", re.IGNORECASE)
_AJAX_HANDLER = "onCiudadFilter"
_ARBITRAGE_KEYWORDS = {"arbitraje", "arbitrage"}

_FALLBACK_LOCATIONS: list[tuple[str, int]] = [
    ("cde", 1),
    ("cheques", 2),
    ("arbitraje", 3),
]


def _code_from_flag(img_tag: Tag | None) -> str | None:
    if img_tag is None:
        return None
    src = img_tag.get("src", "")
    m = _FLAG_RE.search(src)
    return m.group(1).upper() if m else None


def _parse_cotiz_block(block: Tag, fuente: SourceName, tipo: RateType, sucursal: str | None) -> CurrencyRate | None:
    try:
        img = block.find("img")
        code = _code_from_flag(img)
        if not code:
            return None

        texts = list(block.stripped_strings)
        nombre = texts[0] if texts else code

        compra: float | None = None
        venta: float | None = None

        for i, text in enumerate(texts):
            lower = text.lower()
            if lower in ("compra", "buy") and i + 1 < len(texts):
                compra = parse_number(texts[i + 1])
            elif lower in ("venta", "sell") and i + 1 < len(texts):
                venta = parse_number(texts[i + 1])

        if compra is None and venta is None:
            logger.warning("Maxicambios: sin tasas para %s", code)
            return None

        return CurrencyRate(
            moneda=code,
            nombre=nombre,
            compra=compra,
            venta=venta,
            referencial=None,
            tipo=tipo,
            fuente=fuente,
            sucursal=sucursal,
        )
    except Exception as exc:
        logger.warning("Maxicambios: error parseando bloque – %s", exc)
        return None


def _parse_html_fragment(
    html: str,
    fuente: SourceName,
    tipo_default: RateType,
    sucursal: str | None,
) -> list[CurrencyRate]:
    soup = BeautifulSoup(html, "lxml")
    rates: list[CurrencyRate] = []
    seen_codes: set[str] = set()

    tipo = tipo_default
    for h in soup.find_all(re.compile(r"^h[1-6]$")):
        if any(kw in h.get_text(strip=True).lower() for kw in _ARBITRAGE_KEYWORDS):
            tipo = RateType.ARBITRAGE
            break

    # Selector primario: div.cotizDivSmall (verificado en HTML real)
    blocks = soup.find_all("div", class_=lambda c: c and "cotizDivSmall" in c)

    if not blocks:
        blocks = soup.find_all("div", class_=lambda c: c and "shadow_exchange" in c)

    if not blocks:
        flag_imgs = soup.find_all("img", src=_FLAG_RE)
        seen_parents: set[int] = set()
        for img in flag_imgs:
            parent = img.parent
            for _ in range(6):
                if parent is None:
                    break
                if "Compra" in parent.get_text() and "Venta" in parent.get_text():
                    if id(parent) not in seen_parents:
                        seen_parents.add(id(parent))
                        blocks.append(parent)
                    break
                parent = parent.parent

    for block in blocks:
        rate = _parse_cotiz_block(block, fuente, tipo, sucursal)
        if rate and rate.moneda not in seen_codes:
            seen_codes.add(rate.moneda)
            rates.append(rate)

    return rates


def _discover_locations(soup: BeautifulSoup) -> list[tuple[str, int]]:
    locations: list[tuple[str, int]] = []
    for attr in ("data-id", "data-ciudad", "data-ciudad-id"):
        for el in soup.find_all(True, attrs={attr: True}):
            label = el.get_text(strip=True).lower()
            try:
                locations.append((label, int(el.get(attr))))
            except (ValueError, TypeError):
                continue
        if locations:
            return locations
    return _FALLBACK_LOCATIONS


class MaxicambiosScraper(BaseScraper):
    source = SourceName.MAXICAMBIOS
    url = "https://www.maxicambios.com.py/"

    async def parse(self, html: str) -> list[CurrencyRate]:
        return _parse_html_fragment(html, self.source, RateType.CASH, "asuncion")

    async def _fetch_location(
        self,
        client: httpx.AsyncClient,
        label: str,
        ciudad_id: int,
    ) -> list[CurrencyRate]:
        tipo = RateType.ARBITRAGE if any(kw in label for kw in _ARBITRAGE_KEYWORDS) else RateType.CASH
        sucursal = label.lower().replace(" ", "_")

        try:
            response = await client.post(
                self.url,
                data={"ciudad_id": ciudad_id},
                headers={
                    "X-OCTOBER-REQUEST-HANDLER": _AJAX_HANDLER,
                    "X-Requested-With": "XMLHttpRequest",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()

            try:
                payload = response.json()
            except json.JSONDecodeError:
                html_fragment = response.text
            else:
                html_fragment = ""
                if isinstance(payload, dict):
                    for value in payload.values():
                        if isinstance(value, str) and "<" in value:
                            html_fragment = value
                            break

            if not html_fragment:
                logger.warning("Maxicambios: fragmento vacío para sucursal '%s' (id=%d)", label, ciudad_id)
                return []

            rates = _parse_html_fragment(html_fragment, self.source, tipo, sucursal)
            logger.info("Maxicambios: sucursal '%s' → %d cotizaciones", label, len(rates))
            return rates

        except httpx.HTTPStatusError as exc:
            logger.warning("Maxicambios: HTTP %s para sucursal '%s'", exc.response.status_code, label)
            return []
        except httpx.TimeoutException:
            logger.warning("Maxicambios: timeout en sucursal '%s'", label)
            return []
        except Exception as exc:
            logger.warning("Maxicambios: error inesperado en sucursal '%s' – %s", label, exc)
            return []

    async def fetch_and_parse(self, client: httpx.AsyncClient) -> SourceResult:
        all_rates: list[CurrencyRate] = []

        try:
            response = await client.get(
                self.url,
                timeout=self.timeout,
                headers={"User-Agent": settings.USER_AGENT},
            )
            response.raise_for_status()
            main_html = response.text
        except Exception as exc:
            logger.error("Maxicambios: error obteniendo página principal – %s", exc)
            return SourceResult(
                fuente=self.source,
                cotizaciones=[],
                actualizado_en=datetime.now(timezone.utc),
                error=str(exc),
            )

        main_rates = await self.parse(main_html)
        all_rates.extend(main_rates)
        logger.info("Maxicambios: página principal (asuncion) → %d cotizaciones", len(main_rates))

        soup = BeautifulSoup(main_html, "lxml")
        extra_locations = _discover_locations(soup)

        if extra_locations:
            tasks = [self._fetch_location(client, label, cid) for label, cid in extra_locations]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for (label, _cid), result in zip(extra_locations, results):
                if isinstance(result, list):
                    all_rates.extend(result)
                else:
                    logger.warning("Maxicambios: sucursal '%s' error – %s", label, result)

        logger.info("Maxicambios: total de cotizaciones: %d", len(all_rates))
        return SourceResult(
            fuente=self.source,
            cotizaciones=all_rates,
            actualizado_en=datetime.now(timezone.utc),
        )
