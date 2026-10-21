from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.locks import lock_market_writes
from app.models.alerts import AlertEvent, AlertRule
from app.models.news import Article, ArticleKeyword, ArticleRelevance
from app.models.rates import ExchangeRate
from app.services.rates.signals import MarketSignal, detect_price_signals, detect_trend_reversals, link_policy_articles_to_changes


def _rule_signals(session: Session, rule: AlertRule) -> list[MarketSignal]:
    statement = (
        select(ExchangeRate)
        .where(
            ExchangeRate.base_currency == rule.base_currency,
            ExchangeRate.target_currency == rule.target_currency,
            ExchangeRate.rate_date <= date.today(),
        )
        .order_by(ExchangeRate.rate_date.desc())
    )
    rates = list(session.scalars(statement))[::-1]
    observations = [(row.rate_date, row.rate) for row in rates]
    if rule.alert_type in ("won_cost_at_or_below", "won_cost_at_or_above"):
        if not observations:
            return []
        quote_date, foreign_per_won = observations[-1]
        won_cost = Decimal("1") / foreign_per_won
        matches = won_cost <= rule.threshold if rule.alert_type == "won_cost_at_or_below" else won_cost >= rule.threshold
        return [MarketSignal(rule.alert_type, quote_date, won_cost)] if matches else []
    if len(observations) < 2:
        return []

    if rule.alert_type in ("rapid_rise", "rapid_fall"):
        current_date, current_rate = observations[-1]
        baseline_date = current_date - timedelta(days=rule.lookback_days)
        previous = next((row for row in reversed(observations) if row[0] <= baseline_date), None)
        if previous is None:
            return []
        previous_date, previous_rate = previous
        change_percent = (current_rate - previous_rate) / previous_rate * Decimal("100")
        if rule.alert_type == "rapid_rise" and change_percent >= rule.threshold:
            return [MarketSignal("rapid_rise", current_date, change_percent)]
        if rule.alert_type == "rapid_fall" and change_percent <= -rule.threshold:
            return [MarketSignal("rapid_fall", current_date, change_percent)]
        return []

    if rule.alert_type in ("trend_reversal_up", "trend_reversal_down"):
        signals = detect_trend_reversals(observations)
        recent_from = date.today() - timedelta(days=rule.lookback_days)
        return [signal for signal in signals if signal.signal_type == rule.alert_type and signal.occurred_on >= recent_from]

    if rule.alert_type == "change_point_candidate":
        recent_from = date.today() - timedelta(days=rule.lookback_days)
        return [signal for signal in detect_price_signals(observations, rule.threshold)
                if signal.signal_type == "change_point_candidate" and signal.occurred_on >= recent_from]

    if rule.alert_type == "policy_price_link":
        price_signals = [
            signal
            for signal in detect_price_signals(observations, rule.threshold)
            if signal.signal_type == "change_point_candidate"
        ]
        if not price_signals:
            return []
        article_dates = list(
            session.scalars(
                select(Article.published_at)
                .join(ArticleKeyword, ArticleKeyword.article_id == Article.id)
                .join(ArticleRelevance, ArticleRelevance.article_id == Article.id)
                .where(
                    ArticleKeyword.category == "policy",
                    Article.published_at.is_not(None),
                    ArticleRelevance.base_currency == rule.base_currency,
                    ArticleRelevance.target_currency == rule.target_currency,
                    ArticleRelevance.score > 0,
                )
                .distinct()
            )
        )
        publication_dates = [published_at.date() for published_at in article_dates if published_at is not None]
        pairs = link_policy_articles_to_changes(
            publication_dates,
            [signal.occurred_on for signal in price_signals],
            window_days=rule.lookback_days,
        )
        changes_by_date = {signal.occurred_on: signal for signal in price_signals}
        linked_dates = {changed_on for _, changed_on in pairs}
        return [
            MarketSignal("policy_price_link", changed_on, changes_by_date[changed_on].observed_value)
            for changed_on in sorted(linked_dates)
            if changed_on >= date.today() - timedelta(days=rule.lookback_days)
        ]

    return []


def evaluate_alert_rules(session: Session) -> int:
    lock_market_writes(session)
    rules = list(session.scalars(select(AlertRule).where(AlertRule.enabled.is_(True))))
    created_count = 0

    for rule in rules:
        for signal in _rule_signals(session, rule):
            day_start = datetime.combine(signal.occurred_on, time.min, tzinfo=timezone.utc)
            day_end = day_start + timedelta(days=1)
            duplicate = session.scalar(
                select(AlertEvent.id).where(
                    AlertEvent.rule_id == rule.id,
                    AlertEvent.alert_type == signal.signal_type,
                    AlertEvent.fired_at >= day_start,
                    AlertEvent.fired_at < day_end,
                )
            )
            if duplicate is not None:
                continue

            unit = "rate units (MA5 minus MA20)" if signal.signal_type.startswith("trend_reversal") else "%"
            message = (
                f"{rule.base_currency}/{rule.target_currency} {signal.signal_type}: "
                f"{signal.observed_value:.4f}{unit}"
            )
            if signal.signal_type.startswith("won_cost_"):
                comparison = "at or below" if signal.signal_type == "won_cost_at_or_below" else "at or above"
                message = (f"1 {rule.target_currency} costs KRW {signal.observed_value:,.4f}, "
                           f"{comparison} your KRW {rule.threshold:,.4f} target (quote {signal.occurred_on}).")
            if signal.signal_type == "policy_price_link":
                message += "; policy article and price change are temporally associated, not proven causal"
            session.add(
                AlertEvent(
                    rule_id=rule.id,
                    base_currency=rule.base_currency,
                    target_currency=rule.target_currency,
                    alert_type=signal.signal_type,
                    measured_value=signal.observed_value,
                    message=message,
                    fired_at=day_start,
                )
            )
            created_count += 1

    session.commit()
    return created_count
