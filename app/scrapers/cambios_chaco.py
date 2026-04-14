import logging
import re

from bs4 import BeautifulSoup

from app.models.schemas import CurrencyRate, RateType, SourceName
from app.scrapers.base import BaseScraper
from app.scrapers.utils import extract_currency_code, parse_number

logger = logging.getLogger(__name__)

# Regex to pull the 3-letter currency code from a URL like /perfil-de-moneda/?currency=USD
_CURRENCY_RE = re.compile(r"currency=([A-Z]{3})", re.IGNORECASE)


def _code_from_link(tag) -> str | None:
    """Return the ISO code from an <a> tag's href, or None."""
    href = tag.get("href", "") if tag else ""
    m = _CURRENCY_RE.search(href)
    if m:
        return m.group(1).upper()
    # Second attempt: look for the code inside the link text itself.
    return extract_currency_code(tag.get_text(strip=True)) if tag else None


def _parse_rate_table(table, rate_type: RateType, source: SourceName) -> list[CurrencyRate]:
    """Parse a single exchange-rate <table> and return CurrencyRate objects."""
    rates: list[CurrencyRate] = []

    rows = table.find_all("tr")
    for row in rows:
        # Skip header rows.
        if row.find("th"):
            continue

        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        try:
            # Column 0: currency name / link.  Column 1: buy.  Column 2: sell.
            name_cell = cells[0]
            link_tag = name_cell.find("a")
            code = _code_from_link(link_tag) if link_tag else extract_currency_code(name_cell.get_text(strip=True))
            currency_name = name_cell.get_text(strip=True)

            if not code:
                logger.warning("CambiosChaco: could not resolve currency code from '%s'", currency_name)
                continue

            buy = parse_number(cells[1].get_text(strip=True))
            sell = parse_number(cells[2].get_text(strip=True))

            rates.append(
                CurrencyRate(
                    moneda=code.upper(),
                    nombre=currency_name,
                    compra=buy,
                    venta=sell,
                    referencial=None,
                    tipo=rate_type,
                    fuente=source,
                    sucursal=None,
                )
            )
        except Exception as exc:
            logger.warning("CambiosChaco: unexpected error parsing row – %s", exc)
            continue

    return rates


class CambiosChacoScraper(BaseScraper):
    source = SourceName.CAMBIOS_CHACO
    url = "https://www.cambioschaco.com.py/"

    async def parse(self, html: str) -> list[CurrencyRate]:
        soup = BeautifulSoup(html, "lxml")
        rates: list[CurrencyRate] = []

        # -----------------------------------------------------------------
        # Strategy: find all tables whose class contains "table-exchange".
        # The site typically has two: one for spot rates and one for arbitrage.
        # -----------------------------------------------------------------
        exchange_tables = soup.find_all("table", class_=lambda c: c and "table-exchange" in " ".join(c))

        if not exchange_tables:
            # Broader fallback: any table inside a div that looks like a rate section.
            logger.debug("CambiosChaco: 'table-exchange' class not found – trying fallback")
            exchange_tables = soup.find_all("table")

        if not exchange_tables:
            logger.warning("CambiosChaco: no exchange tables found in the page")
            return rates

        # Heuristic: the first table is the main spot table; the second (if present)
        # is arbitrage.  We distinguish them by checking whether a heading nearby
        # contains "arbitraje".
        for idx, table in enumerate(exchange_tables):
            # Look for a heading immediately before the table to decide the rate type.
            rate_type = RateType.CASH
            # Walk back through previous siblings looking for a heading tag.
            for sibling in table.find_previous_siblings():
                text = sibling.get_text(strip=True).lower()
                if text:
                    if "arbitraje" in text or "arbitrage" in text:
                        rate_type = RateType.ARBITRAGE
                    break

            # If we couldn't find a heading, fall back to position: first = CASH, rest = ARBITRAGE.
            if idx > 0 and rate_type == RateType.CASH:
                # No heading found but there are multiple tables – treat subsequent ones as arbitrage.
                rate_type = RateType.ARBITRAGE

            table_rates = _parse_rate_table(table, rate_type, self.source)
            rates.extend(table_rates)
            logger.debug("CambiosChaco: table %d (%s) yielded %d rates", idx, rate_type.value, len(table_rates))

        logger.info("CambiosChaco: parsed %d rates total", len(rates))
        return rates
