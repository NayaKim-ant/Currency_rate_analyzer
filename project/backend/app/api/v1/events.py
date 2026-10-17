from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.currencies import HOME_CURRENCY
from app.db.session import get_db
from app.models.market import MarketEvent

router = APIRouter(prefix="/events", tags=["events"])


@router.get("")
def list_events(
    target_currency: str | None = Query(default=None, min_length=3, max_length=3),
    base_currency: str = Query(default=HOME_CURRENCY, min_length=3, max_length=3),
    days: int = Query(default=30, ge=1, le=3650),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    statement = (
        select(MarketEvent)
        .where(MarketEvent.occurred_at >= cutoff, MarketEvent.base_currency == base_currency.upper())
        .order_by(MarketEvent.occurred_at.desc())
        .limit(limit)
    )
    if target_currency:
        statement = statement.where(MarketEvent.target_currency == target_currency.upper())

    return [
        {
            "id": event.id,
            "base_currency": event.base_currency,
            "target_currency": event.target_currency,
            "event_type": event.event_type,
            "title": event.title,
            "description": event.description,
            "occurred_at": event.occurred_at,
            "article_id": event.article_id,
            "confidence": event.confidence,
        }
        for event in db.scalars(statement)
    ]
