import html
import logging
import re
import xml.etree.ElementTree as ElementTree
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.currencies import HOME_CURRENCY, SUPPORTED_CURRENCIES
from app.db.locks import lock_market_writes
from app.models.market import Article, ArticleKeyword, ArticleRelevance
from app.services.relevance import score_article

logger = logging.getLogger(__name__)
NEWS_URL = "https://news.google.com/rss/search"
NEWS_QUERY = "exchange rate dollar euro pound yen yuan won central bank inflation interest rate"
USER_AGENT = "basis-market-research/1.0"


@dataclass(frozen=True)
class NewsArticleData:
    title: str
    summary: str
    url: str
    published_at: datetime | None


class _ArticleTextParser(HTMLParser):
    _SKIP_TAGS = {"script", "style", "nav", "header", "footer", "aside", "form", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._content_depth = 0
        self._all_parts: list[str] = []
        self._content_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        elif not self._skip_depth and tag in {"article", "main"}:
            self._content_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif not self._skip_depth and tag in {"article", "main"} and self._content_depth:
            self._content_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = " ".join(html.unescape(data).split())
        if not text:
            return
        self._all_parts.append(text)
        if self._content_depth:
            self._content_parts.append(text)

    def text(self, max_length: int = 5000) -> str:
        parts = self._content_parts or self._all_parts
        return " ".join(parts)[:max_length]


def _parse_published(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_news_rss(xml_content: bytes | str, limit: int = 100) -> list[NewsArticleData]:
    root = ElementTree.fromstring(xml_content)
    articles: list[NewsArticleData] = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        if not title or not url:
            continue
        summary_html = item.findtext("description") or ""
        summary = " ".join(_ArticleTextParserText(summary_html).split())
        articles.append(
            NewsArticleData(
                title=title,
                summary=summary[:2000],
                url=url,
                published_at=_parse_published((item.findtext("pubDate") or "").strip()),
            )
        )
        if len(articles) >= limit:
            break
    return articles


def _ArticleTextParserText(markup: str) -> str:
    parser = _ArticleTextParser()
    parser.feed(markup)
    return parser.text(2000)


def fetch_article_body(url: str) -> str:
    response = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=12.0, follow_redirects=True)
    response.raise_for_status()
    parser = _ArticleTextParser()
    parser.feed(response.text)
    return parser.text()


def fetch_news_articles(
    limit: int = 100,
    start_date: date | None = None,
    end_date: date | None = None,
    include_body: bool = True,
) -> list[tuple[NewsArticleData, str]]:
    if (start_date is None) != (end_date is None):
        raise ValueError("start_date and end_date must be provided together")
    query = NEWS_QUERY
    if start_date is not None and end_date is not None:
        if end_date < start_date:
            raise ValueError("end_date must not be earlier than start_date")
        query += f" after:{(start_date - timedelta(days=1)).isoformat()} before:{(end_date + timedelta(days=1)).isoformat()}"
    response = httpx.get(
        NEWS_URL,
        params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"},
        headers={"User-Agent": USER_AGENT},
        timeout=20.0,
    )
    response.raise_for_status()
    rss_articles = parse_news_rss(response.content, limit)
    if not include_body:
        return [(article, "") for article in rss_articles]

    def fetch_body(article: NewsArticleData) -> tuple[NewsArticleData, str]:
        try:
            return article, fetch_article_body(article.url)
        except (httpx.HTTPError, UnicodeError, ValueError) as error:
            logger.info("Article body unavailable for %s: %s", article.url, error)
            return article, ""

    with ThreadPoolExecutor(max_workers=8, thread_name_prefix="news-fetch") as executor:
        return list(executor.map(fetch_body, rss_articles))


def iter_news_history_batches(
    days: int = 90,
    batch_days: int = 7,
    include_body: bool = True,
) -> Iterator[list[tuple[NewsArticleData, str]]]:
    if days < 1 or batch_days < 1:
        raise ValueError("days and batch_days must be at least one")

    end_date = date.today()
    first_date = end_date - timedelta(days=days - 1)
    seen_urls: set[str] = set()
    batch_start = first_date
    while batch_start <= end_date:
        batch_end = min(batch_start + timedelta(days=batch_days - 1), end_date)
        batch_articles: list[tuple[NewsArticleData, str]] = []
        for article, content in fetch_news_articles(
            limit=100,
            start_date=batch_start,
            end_date=batch_end,
            include_body=include_body,
        ):
            if article.published_at is not None and not batch_start <= article.published_at.date() <= batch_end:
                continue
            if article.url in seen_urls:
                continue
            seen_urls.add(article.url)
            batch_articles.append((article, content))
        yield batch_articles
        batch_start = batch_end + timedelta(days=1)


def fetch_news_history(
    days: int = 90,
    batch_days: int = 7,
    include_body: bool = True,
) -> list[tuple[NewsArticleData, str]]:
    return [
        article
        for batch in iter_news_history_batches(days, batch_days, include_body)
        for article in batch
    ]


def store_news_articles(
    session: Session, articles: Sequence[tuple[NewsArticleData, str]], base_currency: str = HOME_CURRENCY,
) -> int:
    base_currency = base_currency.upper()
    lock_market_writes(session)
    for article_data, content in articles:
        article = session.scalar(select(Article).where(Article.url == article_data.url))
        if article is None:
            article = Article(
                source="Google News RSS",
                title=article_data.title,
                summary=article_data.summary,
                content=content or None,
                url=article_data.url,
                published_at=article_data.published_at,
            )
            session.add(article)
            session.flush()
        else:
            article.title = article_data.title
            article.summary = article_data.summary
            article.content = content or article.content
            article.published_at = article_data.published_at or article.published_at

        keywords_by_category: set[tuple[str, str]] = set()
        for currency in SUPPORTED_CURRENCIES:
            if currency == base_currency:
                continue
            relevance = score_article(article.title, article.content or article.summary, currency)
            row = session.scalar(
                select(ArticleRelevance).where(
                    ArticleRelevance.article_id == article.id,
                    ArticleRelevance.base_currency == base_currency,
                    ArticleRelevance.target_currency == currency,
                )
            )
            if row is None:
                row = ArticleRelevance(
                    article_id=article.id,
                    base_currency=base_currency,
                    target_currency=currency,
                    score=relevance.score,
                    matched_keywords=list(relevance.matched_keywords),
                )
                session.add(row)
            else:
                row.score = relevance.score
                row.matched_keywords = list(relevance.matched_keywords)

            for keyword in relevance.matched_keywords:
                category = "policy" if keyword in relevance.policy_keywords else "general"
                keywords_by_category.add((keyword, category))

        for keyword, category in sorted(keywords_by_category):
            keyword_row = session.scalar(
                select(ArticleKeyword).where(
                    ArticleKeyword.article_id == article.id,
                    ArticleKeyword.keyword == keyword,
                    ArticleKeyword.category == category,
                )
            )
            if keyword_row is None:
                    session.add(
                        ArticleKeyword(
                            article_id=article.id,
                            keyword=keyword,
                            category=category,
                        )
                    )

    session.commit()
    return len(articles)
