from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.market import Article, ArticleKeyword, ArticleRelevance
from app.services.news import NewsArticleData, fetch_news_history, parse_news_rss, store_news_articles


def test_parse_news_rss_reads_title_summary_url_and_publication_date() -> None:
    rss = """<rss><channel><item>
      <title>Central bank reviews interest rate policy</title>
      <link>https://example.test/rate-policy</link>
      <description><![CDATA[<p>Dollar and Korean won market update.</p>]]></description>
      <pubDate>Thu, 15 Oct 2026 09:30:00 GMT</pubDate>
    </item></channel></rss>"""

    articles = parse_news_rss(rss)

    assert len(articles) == 1
    assert articles[0].title == "Central bank reviews interest rate policy"
    assert "Dollar and Korean won market update." in articles[0].summary
    assert articles[0].published_at == datetime(2026, 10, 15, 9, 30, tzinfo=timezone.utc)


def test_store_news_upserts_article_relevance_and_policy_keywords(test_database) -> None:
    article = NewsArticleData(
        title="Central bank reviews interest rate policy",
        summary="Korean won market update",
        url="https://example.test/unique-policy-story",
        published_at=datetime(2026, 10, 15, 9, 30, tzinfo=timezone.utc),
    )
    with Session(test_database) as session:
        assert store_news_articles(session, [(article, "The dollar moves after an interest rate decision.")]) == 1
        assert store_news_articles(session, [(article, "Updated article body with monetary policy details.")]) == 1
        articles = list(session.scalars(select(Article)))
        relevance = list(session.scalars(select(ArticleRelevance).where(ArticleRelevance.target_currency == "USD")))
        policy_keywords = list(session.scalars(select(ArticleKeyword).where(ArticleKeyword.category == "policy")))

    assert len(articles) == 1
    assert articles[0].content == "Updated article body with monetary policy details."
    assert len(relevance) == 1
    assert relevance[0].matched_keywords
    assert policy_keywords


def test_news_history_searches_non_overlapping_windows_and_deduplicates(monkeypatch) -> None:
    today = date.today()
    first_day = today - timedelta(days=14)
    windows: list[tuple[date, date]] = []
    body_flags: list[bool] = []
    first_article = NewsArticleData("Policy update", "", "https://example.test/one", datetime.combine(first_day, datetime.min.time(), timezone.utc))
    final_article = NewsArticleData("Rate update", "", "https://example.test/two", datetime.combine(today, datetime.min.time(), timezone.utc))

    def fetch_window(limit=100, start_date=None, end_date=None, include_body=True):
        windows.append((start_date, end_date))
        body_flags.append(include_body)
        return [(first_article, "body"), (final_article, "body")]

    monkeypatch.setattr("app.services.news.fetch_news_articles", fetch_window)

    result = fetch_news_history(days=15, batch_days=7, include_body=False)

    assert windows == [
        (first_day, today - timedelta(days=8)),
        (today - timedelta(days=7), today - timedelta(days=1)),
        (today, today),
    ]
    assert body_flags == [False, False, False]
    assert [article.url for article, _ in result] == [first_article.url, final_article.url]
