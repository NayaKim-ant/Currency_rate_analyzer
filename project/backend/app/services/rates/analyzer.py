"""Persist reproducible trend snapshots and timeline events from stored inputs."""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.locks import lock_market_writes
from app.models.news import Article, ArticleKeyword, ArticleRelevance
from app.models.rates import ExchangeRate, MarketEvent, TrendSnapshot
from app.services.rates.signals import detect_price_signals, detect_trend_reversals
from app.services.rates.trends import classify_trend, moving_average


def analyze_market(session: Session, include_alerts: bool = True) -> dict[str, int]:
    """Refresh derived rows; repeated runs reuse each pair/date/event identity."""
    lock_market_writes(session)
    snapshots = 0
    created_events = 0
    pairs = session.execute(select(ExchangeRate.base_currency, ExchangeRate.target_currency).distinct()).all()
    for base, target in pairs:
        rates = list(session.scalars(select(ExchangeRate).where(
            ExchangeRate.base_currency == base,
            ExchangeRate.target_currency == target,
        ).order_by(ExchangeRate.rate_date)))
        observations = [(row.rate_date, row.rate) for row in rates]
        values = [row.rate for row in rates]
        averages = {window: moving_average(values, window) for window in (5, 20, 60)}
        signals = detect_price_signals(observations) + detect_trend_reversals(observations)
        change_dates = {signal.occurred_on for signal in signals if signal.signal_type == "change_point_candidate"}
        existing_snapshots = {row.as_of_date: row for row in session.scalars(select(TrendSnapshot).where(
            TrendSnapshot.base_currency == base, TrendSnapshot.target_currency == target,
        ))}
        for index, rate in enumerate(rates):
            snapshot = existing_snapshots.get(rate.rate_date)
            if snapshot is None:
                snapshot = TrendSnapshot(base_currency=base, target_currency=target, as_of_date=rate.rate_date)
                session.add(snapshot)
            snapshot.ma_5, snapshot.ma_20, snapshot.ma_60 = (averages[window][index] for window in (5, 20, 60))
            snapshot.trend_state = classify_trend(snapshot.ma_5, snapshot.ma_20, snapshot.ma_60)
            snapshot.daily_change_percent = (
                (rate.rate - values[index - 1]) / values[index - 1] * Decimal("100") if index else None
            )
            snapshot.change_point = rate.rate_date in change_dates
            snapshots += 1

        existing_events = {}
        expected_events = set()
        for event in session.scalars(select(MarketEvent).where(
            MarketEvent.base_currency == base, MarketEvent.target_currency == target,
        )):
            existing_events[(event.event_type, event.occurred_at.date(), event.article_id)] = event

        def save_event(event_type: str, occurred_on: date, article_id: int | None, description: str) -> None:
            nonlocal created_events
            key = (event_type, occurred_on, article_id)
            expected_events.add(key)
            event = existing_events.get(key)
            if event is None:
                event = MarketEvent(
                    base_currency=base, target_currency=target, event_type=event_type,
                    occurred_at=datetime.combine(occurred_on, time.min, tzinfo=timezone.utc),
                    article_id=article_id,
                )
                session.add(event)
                existing_events[key] = event
                created_events += 1
            event.title = f"{base}/{target} {event_type}"
            event.description = description

        for signal in signals:
            unit = "rate units (MA5 minus MA20)" if signal.signal_type.startswith("trend_reversal") else "% daily change"
            save_event(signal.signal_type, signal.occurred_on, None, f"Rule-based signal: {signal.observed_value:.5f} {unit}")

        policy_articles = session.scalars(select(Article).join(
            ArticleRelevance, ArticleRelevance.article_id == Article.id,
        ).where(
            ArticleRelevance.base_currency == base, ArticleRelevance.target_currency == target,
            ArticleRelevance.score > 0, Article.published_at.is_not(None),
            select(ArticleKeyword.id).where(
                ArticleKeyword.article_id == Article.id, ArticleKeyword.category == "policy",
            ).exists(),
        ))
        for article in policy_articles:
            published_on = article.published_at.date()
            for changed_on in change_dates:
                if abs(changed_on - published_on) <= timedelta(days=2):
                    save_event("policy_price_link", changed_on, article.id,
                               f"Policy article: {article.title}. Published within two days of a price change; "
                               "temporal association does not establish causation.")

        generated_types = {"rapid_rise", "rapid_fall", "change_point_candidate",
                           "trend_reversal_up", "trend_reversal_down", "policy_price_link"}
        for key, event in existing_events.items():
            if event.event_type in generated_types and key not in expected_events:
                session.delete(event)

    session.commit()
    alerts = 0
    if include_alerts:
        from app.services.alerts.engine import evaluate_alert_rules
        alerts = evaluate_alert_rules(session)
    return {"snapshots": snapshots, "events_created": created_events, "alerts_created": alerts}
