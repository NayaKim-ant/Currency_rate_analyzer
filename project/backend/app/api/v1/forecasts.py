from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.forecasts import ForecastRun
from app.models.news import NewsFact
from app.models.rates import ExchangeRate
from app.schemas.forecasts import ForecastResponse
from app.services.forecasting.outlook import filter_news_hints, timing_signal
from app.services.forecasting.scorecard import forecast_at_horizon, scorecard
from app.services.forecasting.leaderboard import build_leaderboard
from app.services.news.facts import VERSION, as_utc

router = APIRouter(prefix="/forecasts", tags=["forecasts"])


@router.get("", response_model=ForecastResponse)
def latest_forecast(
    target_currency: str = Query(default="USD", pattern="^(USD|AUD|CAD|CHF|CNY|EUR|GBP|JPY)$"),
    horizon: int = Query(default=1, ge=1, le=10),
    db: Session = Depends(get_db),
) -> dict:
    now = datetime.now(timezone.utc)
    if horizon not in (1, 3, 5, 10):
        raise HTTPException(status_code=422, detail="Choose a horizon of 1, 3, 5, or 10 trading days")
    run = db.scalar(
        select(ForecastRun)
        .where(ForecastRun.target_currency == target_currency)
        .order_by(ForecastRun.id.desc())
        .limit(1)
    )
    candidates = db.scalars(
        select(NewsFact)
        .where(
            NewsFact.available_at <= now,
            NewsFact.superseded_at.is_(None),
            or_(NewsFact.published_at >= now - timedelta(days=7), NewsFact.published_at.is_(None)),
        )
        .order_by(NewsFact.available_at.desc(), NewsFact.id.desc())
    )
    hints, seen_count = filter_news_hints(candidates, target_currency, max_hints=8)
    latest_rate = db.scalar(
        select(ExchangeRate)
        .where(ExchangeRate.base_currency == "KRW", ExchangeRate.target_currency == target_currency)
        .order_by(ExchangeRate.rate_date.desc())
        .limit(1)
    )
    stale = bool(
        run
        and (
            (latest_rate and latest_rate.rate_date > run.as_of_date)
            or any(as_utc(hint["available_at"]) > as_utc(run.created_at) for hint in hints)
        )
    )
    selected = forecast_at_horizon(run.payload, horizon) if run else None
    outlook = (
        {
            str(h): timing_signal(forecast_at_horizon(run.payload, h), run.as_of_date, h, now, stale)
            for h in (1, 3, 5, 10)
        }
        if run
        else {}
    )
    evidence = scorecard(db, target_currency,
        configuration=selected.get("configuration", {}) if selected else {}, horizon=horizon,
        comparison_models=list(selected.get("candidate_forecasts", {})) if selected else None)
    return {
        "status": selected.get("status") if selected else "not_trained",
        "target_currency": target_currency,
        "selected_horizon": horizon,
        "outlook": outlook,
        "run_id": run.id if run else None,
        "created_at": run.created_at if run else None,
        "forecast": run.payload if run else None,
        "stale": stale,
        "hints": hints,
        "recent_factor_count": seen_count,
        "extractor": VERSION,
        "scorecard": evidence,
        "leaderboard": build_leaderboard(selected, evidence, horizon),
    }
