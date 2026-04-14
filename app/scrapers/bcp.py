import logging
import re

from bs4 import BeautifulSoup

from app.models.schemas import CurrencyRate, RateType, SourceName
from app.scrapers.base import BaseScraper
from app.scrapers.utils import bcp_name_to_code, extract_currency_code, parse_number

logger = logging.getLogger(__name__)


class BCPScraper(BaseScraper):
    source = SourceName.BCP
    url = "https://www.bcp.gov.py/webapps/web/cotizacion/monedas"

    async def parse(self, html: str) -> list[CurrencyRate]:
        soup = BeautifulSoup(html, "lxml")
        rates: list[CurrencyRate] = []

        table = soup.find("table")
        if table is None:
            logger.warning("BCP: no <table> found in the page")
            return rates

        rows = table.find_all("tr")
        for row in rows:
            if row.find("th"):
                continue

            cells = row.find_all("td")
            if len(cells) < 4:
                continue

            try:
                # Real column layout: 0=nombre completo, 1=codigo ISO, 2=ME/USD, 3=Gs/ME
                raw_name = cells[0].get_text(strip=True).replace("\xa0", " ").strip()
                raw_code = cells[1].get_text(strip=True)
                raw_pyg = cells[3].get_text(strip=True)

                code = raw_code if (raw_code and len(raw_code) == 3 and raw_code.isalpha()) else None
                if code is None:
                    code = bcp_name_to_code(raw_name)
                if not code:
                    logger.warning("BCP: no se pudo resolver el codigo para '%s'", raw_name)
                    continue

                # Limpiar nombre: eliminar espacios extras, saltos de línea y asteriscos
                nombre = re.sub(r"\s+", " ", raw_name).replace("*", "").strip().title() if raw_name else code

                pyg_rate = parse_number(raw_pyg)
                if pyg_rate is None:
                    logger.warning("BCP: no se pudo parsear la tasa '%s' para %s", raw_pyg, code)
                    continue

                rates.append(
                    CurrencyRate(
                        moneda=code.upper(),
                        nombre=nombre,
                        compra=None,
                        venta=None,
                        referencial=pyg_rate,
                        tipo=RateType.REFERENTIAL,
                        fuente=self.source,
                        sucursal=None,
                    )
                )
            except Exception as exc:
                logger.warning("BCP: error inesperado procesando fila – %s", exc)
                continue

        logger.info("BCP: %d cotizaciones procesadas", len(rates))
        return rates
