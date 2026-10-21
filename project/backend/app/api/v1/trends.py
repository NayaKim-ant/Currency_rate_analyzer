from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.currencies import HOME_CURRENCY
from app.db.session import get_db
from app.models.rates import TrendSnapshot
from app.schemas.trends import TrendSnapshotResponse

router = APIRouter(prefix="/trends", tags=["trends"])


@router.get("", response_model=list[TrendSnapshotResponse])
def list_trends(
    base_currency: str = Query(default=HOME_CURRENCY, min_length=3, max_length=3),
    target_currency: str | None = Query(default=None, min_length=3, max_length=3),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    statement = select(TrendSnapshot).where(TrendSnapshot.base_currency == base_currency.upper())
    if target_currency:
        statement = statement.where(TrendSnapshot.target_currency == target_currency.upper())
    rows = db.scalars(statement.order_by(TrendSnapshot.as_of_date.desc()))
    latest = {}
    for row in rows:
        if row.target_currency not in latest:
            latest[row.target_currency] = {
                "base_currency": row.base_currency,
                "target_currency": row.target_currency,
                "as_of_date": row.as_of_date,
                "trend_state": row.trend_state,
                "ma_5": row.ma_5,
                "ma_20": row.ma_20,
                "ma_60": row.ma_60,
                "daily_change_percent": row.daily_change_percent,
                "change_point": row.change_point,
                "method": "MA5 > MA20 > MA60: uptrend; MA5 < MA20 < MA60: downtrend; otherwise neutral. "
                          "Incomplete windows: insufficient_data. Change point: absolute daily change >= 2%.",
            }
    return [latest[currency] for currency in sorted(latest)]
