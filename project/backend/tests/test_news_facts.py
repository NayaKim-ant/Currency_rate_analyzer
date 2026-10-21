from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.news import Article, NewsFact
from app.services.news.facts import extract_candidates, extract_news_facts


def test_extracts_exact_evidence_figures_and_distinguishes_expectations():
    text = "The Federal Reserve raised interest rates by 25 basis points."
    fact = extract_candidates(text, "")[0]
    assert fact.evidence == text
    assert fact.factor == "interest_rates" and fact.currencies == ["USD"]
    assert fact.direction == "increase" and fact.claim_type == "reported"
    assert fact.figures[0]["value"] == 25
    expected = extract_candidates("The Fed is expected to cut interest rates by 0.25%.", "")[0]
    assert expected.claim_type == "forward_looking"
    assert expected.figures[0]["value"] == 0.25


def test_negation_and_multiple_factors_do_not_invent_a_direction():
    fact = extract_candidates("The Fed did not raise interest rates.", "")[0]
    assert fact.direction == "unspecified"
    facts = extract_candidates("The Fed raised interest rates as inflation fell to 2%.", "")
    assert {fact.factor for fact in facts} == {"interest_rates", "inflation"}
    assert all(f.direction == "unspecified" for f in facts)
    assert all(not value["assigned"] for f in facts for value in f.figures)
    assert extract_candidates("Tell us about inflation", "")[0].currencies == []


def test_evidence_is_not_backdated_and_revisions_keep_their_vintages(test_database):
    now = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
    with Session(test_database) as session:
        article = Article(title="US inflation rose to 3%.", source="test", url="https://example.test/macro",
                          fetched_at=now-timedelta(days=1), published_at=now-timedelta(days=80))
        session.add(article); session.commit()
        assert extract_news_facts(session, now) == 1
        assert extract_news_facts(session, now+timedelta(hours=1)) == 0
        first = session.scalar(select(NewsFact))
        assert first.available_at.replace(tzinfo=timezone.utc) == now
        article.title = "US inflation fell to 2%."; session.commit()
        assert extract_news_facts(session, now+timedelta(days=1)) == 1
        session.refresh(first)
        assert first.superseded_at is not None and first.evidence == "US inflation rose to 3%."
        article.title = "US inflation rose to 3%."; session.commit()
        assert extract_news_facts(session, now+timedelta(days=2)) == 1
        assert extract_news_facts(session, now+timedelta(days=2, hours=1)) == 0
        rows = list(session.scalars(select(NewsFact)))
        assert len(rows) == 3 and sum(row.superseded_at is None for row in rows) == 1


def test_forecast_api_can_serve_without_ml_training_and_rejects_unsupported_pair(client):
    assert client.get("/api/v1/forecasts").json()["status"] == "not_trained"
    assert client.get("/api/v1/forecasts?target_currency=KRW").status_code == 422
