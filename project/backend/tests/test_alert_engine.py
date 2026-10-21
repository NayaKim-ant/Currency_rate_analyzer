from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alerts import AlertEvent, AlertRule
from app.models.news import Article, ArticleKeyword, ArticleRelevance
from app.models.rates import ExchangeRate
from app.services.alerts.engine import evaluate_alert_rules


def test_alert_evaluator_records_a_rise_once(test_database) -> None:
    today = date.today()
    with Session(test_database) as session:
        session.add(
            AlertRule(
                base_currency="USD",
                target_currency="KRW",
                alert_type="rapid_rise",
                threshold=Decimal("2"),
                lookback_days=1,
            )
        )
        session.add_all(
            [
                ExchangeRate(
                    base_currency="USD",
                    target_currency="KRW",
                    rate_date=today - timedelta(days=1),
                    rate=Decimal("100"),
                    source="test",
                ),
                ExchangeRate(
                    base_currency="USD",
                    target_currency="KRW",
                    rate_date=today,
                    rate=Decimal("103"),
                    source="test",
                ),
            ]
        )
        session.commit()

        assert evaluate_alert_rules(session) == 1
        assert evaluate_alert_rules(session) == 0
        event = session.scalar(select(AlertEvent))

    assert event is not None
    assert event.alert_type == "rapid_rise"
    assert event.measured_value == Decimal("3")


def test_change_point_rule_uses_configured_threshold_once(test_database):
    with Session(test_database) as session:
        session.add(AlertRule(base_currency="USD", target_currency="JPY", alert_type="change_point_candidate",
                              threshold=Decimal("4"), lookback_days=2))
        session.add_all([
            ExchangeRate(base_currency="USD", target_currency="JPY", rate_date=date.today() - timedelta(days=1),
                         rate=Decimal("100"), source="test"),
            ExchangeRate(base_currency="USD", target_currency="JPY", rate_date=date.today(),
                         rate=Decimal("95"), source="test"),
        ])
        session.commit()
        assert evaluate_alert_rules(session) == 1
        assert evaluate_alert_rules(session) == 0
        event = session.scalar(select(AlertEvent))
        assert event.alert_type == "change_point_candidate"
        assert event.measured_value == Decimal("-5")


def test_policy_alert_uses_pair_relevance_and_deduplicates_multiple_articles(test_database):
    with Session(test_database, autoflush=False) as session:
        session.add(AlertRule(base_currency="USD", target_currency="KRW", alert_type="policy_price_link",
                              threshold=Decimal("2"), lookback_days=3))
        session.add_all([
            ExchangeRate(base_currency="USD", target_currency="KRW", rate_date=date.today() - timedelta(days=1),
                         rate=Decimal("100"), source="test"),
            ExchangeRate(base_currency="USD", target_currency="KRW", rate_date=date.today(),
                         rate=Decimal("103"), source="test"),
        ])
        article = Article(title="Euro policy", source="test", url="https://example.test/eur",
                          published_at=datetime.combine(date.today(), time.min, tzinfo=timezone.utc))
        session.add(article)
        session.flush()
        session.add(ArticleKeyword(article_id=article.id, category="policy", keyword="central bank"))
        session.add(ArticleRelevance(article_id=article.id, base_currency="USD", target_currency="EUR",
                                     score=Decimal("30"), matched_keywords=["central bank"]))
        session.commit()
        assert evaluate_alert_rules(session) == 0
        for offset in (0, 1):
            article = Article(title="Korea policy", source="test", url=f"https://example.test/krw/{offset}",
                              published_at=datetime.combine(date.today() - timedelta(days=offset), time.min,
                                                            tzinfo=timezone.utc))
            session.add(article)
            session.flush()
            session.add(ArticleKeyword(article_id=article.id, category="policy", keyword="central bank"))
            session.add(ArticleRelevance(article_id=article.id, base_currency="USD", target_currency="KRW",
                                         score=Decimal("30"), matched_keywords=["central bank"]))
        session.commit()
        assert evaluate_alert_rules(session) == 1
        assert evaluate_alert_rules(session) == 0
        assert len(list(session.scalars(select(AlertEvent)))) == 1


def test_alert_lookback_is_calendar_days_including_nontrading_days(test_database):
    with Session(test_database) as session:
        session.add(AlertRule(base_currency="USD", target_currency="KRW", alert_type="rapid_rise",
                              threshold=Decimal("2"), lookback_days=3))
        # A three-calendar-day interval can contain only two observations.
        session.add_all([
            ExchangeRate(base_currency="USD", target_currency="KRW", rate_date=date.today() - timedelta(days=3),
                         rate=Decimal("100"), source="test"),
            ExchangeRate(base_currency="USD", target_currency="KRW", rate_date=date.today(),
                         rate=Decimal("103"), source="test"),
        ])
        session.commit()
        assert evaluate_alert_rules(session) == 1
