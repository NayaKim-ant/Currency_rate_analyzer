from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.currencies import HOME_CURRENCY
from app.db.session import get_db
from app.models.market import Article, ArticleKeyword, ArticleRelevance
from app.schemas.articles import ArticleSearchResult

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("", response_model=list[ArticleSearchResult])
def list_articles(
    target_currency: str = Query(default="USD", min_length=3, max_length=3),
    base_currency: str = Query(default=HOME_CURRENCY, min_length=3, max_length=3),
    days: int = Query(default=30, ge=1, le=3650),
    min_score: float = Query(default=0, ge=0, le=100),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[ArticleSearchResult]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    statement = (
        select(Article, ArticleRelevance)
        .join(ArticleRelevance, ArticleRelevance.article_id == Article.id)
        .where(
            ArticleRelevance.base_currency == base_currency.upper(),
            ArticleRelevance.target_currency == target_currency.upper(),
            ArticleRelevance.score >= min_score,
            func.coalesce(Article.published_at, Article.fetched_at) >= cutoff,
        )
        .order_by(ArticleRelevance.score.desc(), Article.published_at.desc())
        .limit(limit)
    )
    rows = list(db.execute(statement))
    article_ids = [article.id for article, _ in rows]
    policy_by_article: dict[int, list[str]] = {article_id: [] for article_id in article_ids}
    if article_ids:
        keyword_rows = db.execute(
            select(ArticleKeyword.article_id, ArticleKeyword.keyword)
            .where(ArticleKeyword.article_id.in_(article_ids), ArticleKeyword.category == "policy")
            .order_by(ArticleKeyword.keyword)
        )
        for article_id, keyword in keyword_rows:
            policy_by_article[article_id].append(keyword)

    return [
        ArticleSearchResult(
            article_id=article.id,
            source=article.source,
            title=article.title,
            summary=article.summary,
            url=article.url,
            published_at=article.published_at,
            relevance_score=relevance.score,
            matched_keywords=relevance.matched_keywords,
            policy_keywords=policy_by_article[article.id],
        )
        for article, relevance in rows
    ]
