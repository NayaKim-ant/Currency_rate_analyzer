from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models.news import Article, ArticleKeyword, ArticleRelevance
from app.models.rates import MarketEvent

client = TestClient(app)


def test_article_and_event_endpoints_return_related_records(test_database) -> None:
    with Session(test_database) as session:
        article = Article(
            source="test-wire",
            title="Central bank adjusts interest rate outlook",
            summary="Policy update",
            content="The monetary policy decision was reported.",
            url="https://example.test/policy-rate",
            published_at=datetime(2026, 10, 14, tzinfo=timezone.utc),
        )
        session.add(article)
        session.flush()
        session.add_all(
            [
                ArticleRelevance(
                    article_id=article.id,
                    base_currency="USD",
                    target_currency="KRW",
                    score=Decimal("75"),
                    matched_keywords=["central bank", "interest rate"],
                ),
                ArticleKeyword(article_id=article.id, keyword="interest rate", category="policy", weight=Decimal("3")),
                MarketEvent(
                    base_currency="USD",
                    target_currency="KRW",
                    event_type="change_point_candidate",
                    title="Rate moved sharply",
                    occurred_at=datetime(2026, 10, 14, tzinfo=timezone.utc),
                    article_id=article.id,
                    confidence=Decimal("0.8"),
                ),
            ]
        )
        session.commit()

    article_response = client.get("/api/v1/articles?base_currency=USD&target_currency=krw&min_score=50")
    event_response = client.get("/api/v1/events?base_currency=USD&target_currency=krw")

    assert article_response.status_code == 200
    article_result = article_response.json()[0]
    assert article_result["relevance_score"] == "75.0000"
    assert article_result["policy_keywords"] == ["interest rate"]
    assert event_response.status_code == 200
    assert event_response.json()[0]["event_type"] == "change_point_candidate"


def test_article_window_uses_publication_date_with_fallback_for_undated_articles(test_database):
    now = datetime.now(timezone.utc)
    with Session(test_database) as session:
        for name, published, fetched in [
            ("old-backfill", now - timedelta(days=80), now),
            ("recent", now - timedelta(days=1), now),
            ("undated", None, now),
            ("old-undated", None, now - timedelta(days=80)),
        ]:
            article = Article(title=name, url=f"https://example.test/{name}", source="test",
                              published_at=published, fetched_at=fetched)
            session.add(article)
            session.flush()
            session.add(ArticleRelevance(article_id=article.id, base_currency="USD", target_currency="KRW",
                                         score=Decimal("50"), matched_keywords=[]))
        session.commit()
    data = client.get("/api/v1/articles?base_currency=USD&target_currency=KRW&days=30").json()
    assert {article["title"] for article in data} == {"recent", "undated"}
