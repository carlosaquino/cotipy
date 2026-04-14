from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel


class SourceName(str, Enum):
    BCP = "bcp"
    MAXICAMBIOS = "maxicambios"
    CAMBIOS_CHACO = "cambios_chaco"


class RateType(str, Enum):
    REFERENTIAL = "referencial"
    CASH = "efectivo"
    ARBITRAGE = "arbitraje"


class CurrencyRate(BaseModel):
    moneda: str
    nombre: str
    compra: float | None = None
    venta: float | None = None
    referencial: float | None = None
    tipo: RateType
    fuente: SourceName
    sucursal: str | None = None


class SourceResult(BaseModel):
    fuente: SourceName
    cotizaciones: list[CurrencyRate]
    actualizado_en: datetime
    desactualizado: bool = False
    error: str | None = None


class AllRatesResponse(BaseModel):
    fuentes: list[SourceResult]
    actualizado_en: datetime


class HistoryEntry(BaseModel):
    id: int
    moneda: str
    nombre: str
    fuente: SourceName
    compra: float | None
    venta: float | None
    referencial: float | None
    tipo: RateType
    sucursal: str | None
    registrado_en: datetime

    model_config = {"from_attributes": True}


class HistoryResponse(BaseModel):
    moneda: str
    registros: list[HistoryEntry]
    total: int


class DailyAverage(BaseModel):
    fecha: date
    fuente: SourceName
    moneda: str
    compra_promedio: float | None
    venta_promedio: float | None
    referencial_promedio: float | None
    sucursal: str | None


class DailyAverageResponse(BaseModel):
    moneda: str
    promedios: list[DailyAverage]


class HealthResponse(BaseModel):
    estado: str
    version: str
    fuentes: dict[str, str]
    base_de_datos: str
