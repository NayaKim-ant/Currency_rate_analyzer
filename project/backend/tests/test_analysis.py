from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.news import Article, ArticleKeyword, ArticleRelevance
from app.models.rates import ExchangeRate, MarketEvent, TrendSnapshot
from app.services.rates.analyzer import analyze_market


def test_analysis_persists_snapshots_signals_and_policy_links_once(test_database):
    start = date.today() - timedelta(days=60)
    with Session(test_database) as session:
        session.add_all([
            ExchangeRate(base_currency="USD", target_currency="KRW", rate_date=start + timedelta(days=i),
                         rate=Decimal("100") if i < 60 else Decimal("103"), source="test")
            for i in range(61)
        ])
        article = Article(title="Central bank policy", source="test", url="https://example.test/policy",
                          published_at=datetime.combine(date.today(), time.min, tzinfo=timezone.utc))
        session.add(article)
        session.flush()
        session.add(ArticleKeyword(article_id=article.id, keyword="central bank", category="policy"))
        session.add(ArticleRelevance(article_id=article.id, base_currency="USD", target_currency="KRW",
                                     score=Decimal("15"), matched_keywords=["central bank"]))
        session.commit()

        first = analyze_market(session)
        second = analyze_market(session)
        assert first == {"snapshots": 61, "events_created": 3, "alerts_created": 0}
        assert second["events_created"] == 0
        snapshots = list(session.scalars(select(TrendSnapshot).order_by(TrendSnapshot.as_of_date)))
        assert len(snapshots) == 61
        assert snapshots[0].ma_5 is None
        assert snapshots[59].ma_60 == Decimal("100")
        assert snapshots[-1].daily_change_percent == Decimal("3")
        assert snapshots[-1].change_point is True
        events = list(session.scalars(select(MarketEvent)))
        assert {row.event_type for row in events} == {"rapid_rise", "change_point_candidate", "policy_price_link"}
        policy_event = next(row for row in events if row.event_type == "policy_price_link")
        assert policy_event.article_id == article.id
        assert "does not establish causation" in policy_event.description

        # Source corrections must also remove signals that no longer hold.
        latest = session.scalar(select(ExchangeRate).where(ExchangeRate.rate_date == date.today()))
        latest.rate = Decimal("100")
        session.commit()
        analyze_market(session)
        assert list(session.scalars(select(MarketEvent))) == []
        session.refresh(snapshots[-1])
        assert snapshots[-1].change_point is False


def test_trends_api_returns_latest_snapshot_and_explanation(client, test_database):
    with Session(test_database) as session:
        session.add_all([
            TrendSnapshot(base_currency="USD", target_currency="KRW", as_of_date=date.today() - timedelta(days=1),
                          trend_state="neutral"),
            TrendSnapshot(base_currency="USD", target_currency="KRW", as_of_date=date.today(),
                          ma_5=Decimal("103"), ma_20=Decimal("102"), ma_60=Decimal("101"),
                          trend_state="uptrend"),
        ])
        session.commit()
    response = client.get("/api/v1/trends?base_currency=USD&target_currency=krw")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["trend_state"] == "uptrend"
    assert Decimal(str(data[0]["ma_60"])) == Decimal("101")
    assert "MA5 > MA20 > MA60" in data[0]["method"]
    assert client.get("/api/v1/trends?base_currency=USD&target_currency=EUR").json() == []
