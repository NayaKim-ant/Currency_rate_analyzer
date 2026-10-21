"""Populate KRW history and article relevance from existing stored inputs."""

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.currencies import FOREIGN_CURRENCIES, HOME_CURRENCY
from app.db.session import SessionLocal
from app.models.news import Article
from app.models.rates import ExchangeRate
from app.services.news.collector import NewsArticleData, store_news_articles
from app.services.rates.analyzer import analyze_market
from app.services.rates.collector import store_rate_history


def backfill_krw_rates(session: Session, replace_rounded_quotes: bool = False) -> int:
    days = defaultdict(dict)
    for row in session.scalars(select(ExchangeRate).where(ExchangeRate.base_currency == "USD")):
        days[row.rate_date][row.target_currency] = row.rate
    existing_dates = {
        (row.rate_date, row.target_currency)
        for row in session.scalars(
            select(ExchangeRate).where(
                ExchangeRate.base_currency == HOME_CURRENCY,
            )
        )
        if not replace_rounded_quotes or row.source != "frankfurter"
    }
    records = []
    for rate_date, values in sorted(days.items()):
        won_per_dollar = values.get(HOME_CURRENCY)
        if won_per_dollar is None or won_per_dollar <= 0:
            continue
        values["USD"] = Decimal("1")
        for currency in FOREIGN_CURRENCIES:
            if currency not in values or (rate_date, currency) in existing_dates:
                continue
            records.append({
                "base_currency": HOME_CURRENCY,
                "target_currency": currency,
                "rate_date": rate_date,
                "rate": values[currency] / won_per_dollar,
                "source": "frankfurter-cross",
            })
    return store_rate_history(session, records)


def main() -> None:
    with SessionLocal() as session:
        count = backfill_krw_rates(session, replace_rounded_quotes=True)
        articles = [
            (NewsArticleData(a.title, a.summary or "", a.url, a.published_at), a.content or "")
            for a in session.scalars(select(Article))
        ]
        store_news_articles(session, articles)
        results = analyze_market(session)
    print({"krw_rates_added": count, "articles_scored": len(articles), **results})


if __name__ == "__main__":
    main()
