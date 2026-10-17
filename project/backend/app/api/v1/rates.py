from datetime import date, timedelta
from decimal import Decimal
from typing import Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.currencies import HOME_CURRENCY
from app.db.session import get_db
from app.models.market import ExchangeRate
from app.schemas.rates import RatePoint, RateSeriesResponse
from app.services.trends import classify_trend, moving_average

router = APIRouter(prefix="/rates", tags=["rates"])


@router.get("", response_model=RateSeriesResponse)
def get_rates(
    target_currency: str = Query(default="USD", min_length=3, max_length=3),
    base_currency: str = Query(default=HOME_CURRENCY, min_length=3, max_length=3),
    days: int = Query(default=90, ge=1, le=3650),
    quote_direction: Literal["target_per_base", "base_per_target"] = Query(default="target_per_base"),
    db: Session = Depends(get_db),
) -> RateSeriesResponse:
    normalized_base = base_currency.upper()
    normalized_target = target_currency.upper()
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)
    pair_filter = (
        ExchangeRate.base_currency == normalized_base,
        ExchangeRate.target_currency == normalized_target,
    )
    # Include the previous 59 observations so changing the visible window does
    # not change an average for the same date. Weekends need no synthetic rates.
    warmup = list(db.scalars(select(ExchangeRate).where(
        *pair_filter, ExchangeRate.rate_date < start_date,
    ).order_by(ExchangeRate.rate_date.desc()).limit(59)))[::-1]
    statement = (
        select(ExchangeRate)
        .where(
            *pair_filter,
            ExchangeRate.rate_date >= start_date,
            ExchangeRate.rate_date <= end_date,
        )
        .order_by(ExchangeRate.rate_date)
    )
    rows = list(db.scalars(statement))
    values = [row.rate for row in warmup + rows]
    if quote_direction == "base_per_target":
        # Invert each observation before averaging: 1 / MA(rate) is not MA(1 / rate).
        values = [Decimal("1") / value for value in values]
    averages = {window: moving_average(values, window) for window in (5, 20, 60)}
    points = [
        RatePoint(
            rate_date=row.rate_date,
            rate=values[index + len(warmup)],
            ma_5=averages[5][index + len(warmup)],
            ma_20=averages[20][index + len(warmup)],
            ma_60=averages[60][index + len(warmup)],
        )
        for index, row in enumerate(rows)
    ]
    trend_state = "insufficient_data"
    if points:
        latest = points[-1]
        trend_state = classify_trend(latest.ma_5, latest.ma_20, latest.ma_60)

    return RateSeriesResponse(
        base_currency=normalized_base,
        target_currency=normalized_target,
        requested_days=days,
        points=points,
        trend_state=trend_state,
        quote_direction=quote_direction,
        rate_currency=normalized_base if quote_direction == "base_per_target" else normalized_target,
        unit_currency=normalized_target if quote_direction == "base_per_target" else normalized_base,
    )
