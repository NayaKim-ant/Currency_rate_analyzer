from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.forecasts import ForecastRun, NewsFact
from app.models.market import ExchangeRate
from app.services.news_facts import VERSION, as_utc

router = APIRouter(prefix="/forecasts", tags=["forecasts"])


@router.get("")
def latest_forecast(target_currency: str = Query(default="USD", pattern="^(USD|AUD|CAD|CHF|CNY|EUR|GBP|JPY)$"),
                    db: Session = Depends(get_db)) -> dict:
    now = datetime.now(timezone.utc)
    run = db.scalar(select(ForecastRun).where(ForecastRun.target_currency == target_currency).order_by(ForecastRun.id.desc()).limit(1))
    candidates = db.scalars(select(NewsFact).where(
        NewsFact.available_at <= now,
        NewsFact.superseded_at.is_(None),
        or_(NewsFact.published_at >= now-timedelta(days=7), NewsFact.published_at.is_(None)),
    ).order_by(NewsFact.available_at.desc(), NewsFact.id.desc()))
    hints = []
    seen = set()
    for fact in candidates:
        if fact.currencies and not ({"KRW", target_currency} & set(fact.currencies)):
            continue
        key = (fact.factor, fact.evidence.casefold())
        if key in seen:
            continue
        seen.add(key)
        if len(hints) < 8:
            hints.append({"id": fact.id, "factor": fact.factor, "currencies": fact.currencies,
                          "direction": fact.direction, "claim_type": fact.claim_type, "figures": fact.figures,
                          "evidence": fact.evidence, "source_title": fact.source_title, "source_url": fact.source_url,
                          "published_at": fact.published_at, "available_at": fact.available_at})
    latest_rate = db.scalar(select(ExchangeRate).where(ExchangeRate.base_currency == "KRW",
        ExchangeRate.target_currency == target_currency).order_by(ExchangeRate.rate_date.desc()).limit(1))
    stale = bool(run and (latest_rate and latest_rate.rate_date > run.as_of_date
                         or any(as_utc(hint["available_at"]) > as_utc(run.created_at) for hint in hints)))
    return {"status": run.payload.get("status") if run else "not_trained", "target_currency": target_currency,
            "run_id": run.id if run else None, "created_at": run.created_at if run else None,
            "forecast": run.payload if run else None, "stale": stale, "hints": hints,
            "recent_factor_count": len(seen), "extractor": VERSION}
