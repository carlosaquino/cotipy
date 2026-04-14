import logging
from datetime import date, datetime, timezone

from sqlalchemy import func, select

from app.core.database import async_session_factory
from app.models.db_models import ExchangeRate
from app.models.schemas import (
    CurrencyRate,
    DailyAverage,
    DailyAverageResponse,
    HistoryEntry,
    HistoryResponse,
    SourceName,
)

logger = logging.getLogger(__name__)


class HistoryService:
    """Maneja la persistencia y consultas históricas de cotizaciones."""

    async def save_rates(self, rates: list[CurrencyRate]) -> None:
        if not rates:
            return
        now = datetime.now(timezone.utc)
        records = [
            ExchangeRate(
                currency_code=rate.moneda,
                currency_name=rate.nombre,
                buy=rate.compra,
                sell=rate.venta,
                referential=rate.referencial,
                rate_type=rate.tipo.value,
                source=rate.fuente.value,
                location=rate.sucursal,
                recorded_at=now,
            )
            for rate in rates
        ]
        async with async_session_factory() as session:
            session.add_all(records)
            await session.commit()
        logger.info("Guardados %d registros en la base de datos", len(records))

    async def get_history(
        self,
        currency_code: str,
        source: SourceName | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        location: str | None = None,
        limit: int = 100,
    ) -> HistoryResponse:
        stmt = (
            select(ExchangeRate)
            .where(ExchangeRate.currency_code == currency_code.upper())
            .order_by(ExchangeRate.recorded_at.desc())
        )
        if source is not None:
            stmt = stmt.where(ExchangeRate.source == source.value)
        if date_from is not None:
            stmt = stmt.where(func.date(ExchangeRate.recorded_at) >= date_from.isoformat())
        if date_to is not None:
            stmt = stmt.where(func.date(ExchangeRate.recorded_at) <= date_to.isoformat())
        if location is not None:
            stmt = stmt.where(ExchangeRate.location == location)

        count_stmt = select(func.count()).select_from(stmt.subquery())

        async with async_session_factory() as session:
            total = (await session.execute(count_stmt)).scalar_one()
            rows = (await session.execute(stmt.limit(limit))).scalars().all()

        # Mapear columnas del modelo DB a campos del schema
        entries = [
            HistoryEntry(
                id=row.id,
                moneda=row.currency_code,
                nombre=row.currency_name,
                fuente=SourceName(row.source),
                compra=row.buy,
                venta=row.sell,
                referencial=row.referential,
                tipo=row.rate_type,
                sucursal=row.location,
                registrado_en=row.recorded_at,
            )
            for row in rows
        ]

        return HistoryResponse(
            moneda=currency_code.upper(),
            registros=entries,
            total=total,
        )

    async def get_daily_averages(
        self,
        currency_code: str,
        source: SourceName | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> DailyAverageResponse:
        day_col = func.date(ExchangeRate.recorded_at).label("day")
        stmt = (
            select(
                day_col,
                ExchangeRate.source,
                ExchangeRate.currency_code,
                func.avg(ExchangeRate.buy).label("avg_buy"),
                func.avg(ExchangeRate.sell).label("avg_sell"),
                func.avg(ExchangeRate.referential).label("avg_referential"),
                ExchangeRate.location,
            )
            .where(ExchangeRate.currency_code == currency_code.upper())
            .group_by(day_col, ExchangeRate.source, ExchangeRate.currency_code, ExchangeRate.location)
            .order_by(day_col.desc())
        )
        if source is not None:
            stmt = stmt.where(ExchangeRate.source == source.value)
        if date_from is not None:
            stmt = stmt.where(func.date(ExchangeRate.recorded_at) >= date_from.isoformat())
        if date_to is not None:
            stmt = stmt.where(func.date(ExchangeRate.recorded_at) <= date_to.isoformat())

        async with async_session_factory() as session:
            rows = (await session.execute(stmt)).all()

        promedios = [
            DailyAverage(
                fecha=date.fromisoformat(str(row.day)),
                fuente=SourceName(row.source),
                moneda=row.currency_code,
                compra_promedio=row.avg_buy,
                venta_promedio=row.avg_sell,
                referencial_promedio=row.avg_referential,
                sucursal=row.location,
            )
            for row in rows
        ]

        return DailyAverageResponse(
            moneda=currency_code.upper(),
            promedios=promedios,
        )
