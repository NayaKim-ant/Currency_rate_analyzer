from app.services.news.collector import (
    NEWS_QUERY,
    NEWS_URL,
    USER_AGENT,
    NewsArticleData,
    fetch_article_body,
    fetch_news_articles,
    fetch_news_history,
    iter_news_history_batches,
    parse_news_rss,
    store_news_articles,
)
from app.services.news.events import economic_event
from app.services.news.facts import Candidate, extract_candidates, extract_news_facts
from app.services.news.relevance import RelevanceResult, score_article

__all__ = [
    "Candidate",
    "NEWS_QUERY",
    "NEWS_URL",
    "NewsArticleData",
    "RelevanceResult",
    "USER_AGENT",
    "economic_event",
    "extract_candidates",
    "extract_news_facts",
    "fetch_article_body",
    "fetch_news_articles",
    "fetch_news_history",
    "iter_news_history_batches",
    "parse_news_rss",
    "score_article",
    "store_news_articles",
]
