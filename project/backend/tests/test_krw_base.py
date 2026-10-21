from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alerts import AlertEvent
from app.models.news import ArticleRelevance
from app.models.rates import ExchangeRate, MarketEvent
from app.services.rates import collector as collection
from app.services.news.collector import NewsArticleData, store_news_articles
from app.services.rates.analyzer import analyze_market
from app.cli.rebase_krw import backfill_krw_rates


def test_existing_usd_history_rebases_to_foreign_units_per_won_without_overwriting(test_database):
    today = date.today()
    with Session(test_database) as session:
        session.add_all([
            ExchangeRate(base_currency="USD", target_currency="KRW", rate_date=today, rate=Decimal("1250"), source="test"),
            ExchangeRate(base_currency="USD", target_currency="EUR", rate_date=today, rate=Decimal("0.9"), source="test"),
            ExchangeRate(base_currency="USD", target_currency="JPY", rate_date=today, rate=Decimal("150"), source="test"),
            ExchangeRate(base_currency="KRW", target_currency="JPY", rate_date=today, rate=Decimal("0.121"), source="direct"),
        ])
        session.commit()
        assert backfill_krw_rates(session) == 2
        assert backfill_krw_rates(session) == 0
        rows = {r.target_currency: r for r in session.scalars(select(ExchangeRate).where(ExchangeRate.base_currency == "KRW"))}
        assert rows["USD"].rate == Decimal("0.0008")
        assert rows["EUR"].rate == Decimal("0.00072")
        assert rows["JPY"].rate == Decimal("0.121")
        assert "KRW" not in rows


def test_default_collection_derives_precise_krw_quotes_and_excludes_identity_pair(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"rates": {date.today().isoformat(): {"KRW": 1345.9, "EUR": 0.89222}}}

    def get(url, **kwargs):
        captured.update(kwargs["params"])
        return Response()

    monkeypatch.setattr(collection.httpx, "get", get)
    rows = collection.fetch_rate_history(date.today(), date.today())
    assert captured["from"] == "USD"
    assert "KRW" in captured["to"].split(",")
    assert "USD" not in captured["to"].split(",")
    assert rows[0]["base_currency"] == "KRW"
    usd = next(row for row in rows if row["target_currency"] == "USD")
    eur = next(row for row in rows if row["target_currency"] == "EUR")
    assert usd["rate"] == Decimal("1") / Decimal("1345.9")
    assert eur["rate"] == Decimal("0.89222") / Decimal("1345.9")
    assert usd["rate"] != Decimal("0.00074")  # Rounded provider KRW quote loses precision.


def test_default_api_and_trends_use_krw_and_preserve_small_rates(client, test_database):
    with Session(test_database) as session:
        session.add_all([
            ExchangeRate(base_currency="KRW", target_currency="USD", rate_date=date.today() - timedelta(days=59-i),
                         rate=Decimal("0.0007") + Decimal(i) / Decimal("1000000"), source="test")
            for i in range(60)
        ])
        session.commit()
        analyze_market(session)
    payload = client.get("/api/v1/rates?days=30").json()
    assert payload["base_currency"] == "KRW"
    assert payload["target_currency"] == "USD"
    assert Decimal(payload["points"][-1]["rate"]) == Decimal("0.000759")
    assert Decimal(payload["points"][-1]["ma_60"]) == Decimal("0.0007295")
    assert payload["trend_state"] == "uptrend"  # More USD per won: won strengthening.
    assert client.get("/api/v1/trends").json()[0]["base_currency"] == "KRW"


def test_news_and_alert_rules_default_to_krw(client, test_database):
    with Session(test_database) as session:
        article = NewsArticleData("US dollar and euro react to interest rate", "Central bank news",
                                  "https://example.test/krw-base", None)
        store_news_articles(session, [(article, "")])
        relevance = list(session.scalars(select(ArticleRelevance)))
        assert {row.base_currency for row in relevance} == {"KRW"}
        assert {row.target_currency for row in relevance} == {"USD", "AUD", "CAD", "CHF", "CNY", "EUR", "GBP", "JPY"}
    assert len(client.get("/api/v1/articles").json()) == 1
    assert client.get("/api/v1/articles?base_currency=USD").json() == []
    response = client.post("/api/v1/alerts/rules", json={
        "target_currency": "USD", "alert_type": "rapid_rise", "threshold": "2", "lookback_days": 1,
    })
    assert response.status_code == 201
    assert response.json()["base_currency"] == "KRW"


def test_events_and_alerts_do_not_mix_different_base_currencies(client, test_database):
    with Session(test_database) as session:
        for base in ("KRW", "EUR"):
            session.add(MarketEvent(base_currency=base, target_currency="USD", event_type="rapid_rise",
                                    title=f"{base} event", occurred_at=datetime.now(timezone.utc)))
            session.add(AlertEvent(base_currency=base, target_currency="USD", alert_type="rapid_rise",
                                   message=f"{base} alert", fired_at=datetime.now(timezone.utc)))
        session.commit()
    events = client.get("/api/v1/events?target_currency=USD").json()
    alerts = client.get("/api/v1/alerts?target_currency=USD").json()
    assert len(events) == len(alerts) == 1
    assert events[0]["base_currency"] == alerts[0]["base_currency"] == "KRW"


def test_won_cost_quote_recalculates_averages_from_each_daily_cost(client, test_database):
    with Session(test_database) as session:
        session.add_all([
            ExchangeRate(base_currency="KRW", target_currency="USD", rate_date=date.today() - timedelta(days=59-i),
                         rate=Decimal("0.01") if i % 2 == 0 else Decimal("0.005"), source="test")
            for i in range(60)
        ])
        session.commit()
    payload = client.get("/api/v1/rates?quote_direction=base_per_target&days=90").json()
    assert payload["rate_currency"] == "KRW"
    assert payload["unit_currency"] == "USD"
    assert payload["quote_direction"] == "base_per_target"
    latest = payload["points"][-1]
    assert Decimal(latest["rate"]) == Decimal("200")
    assert Decimal(latest["ma_5"]) == Decimal("160")
    assert Decimal(latest["ma_20"]) == Decimal("150")
    assert Decimal(latest["ma_60"]) == Decimal("150")
    assert payload["points"][3]["ma_5"] is None
    short = client.get("/api/v1/rates?quote_direction=base_per_target&days=30").json()
    assert short["points"][-1] == latest
