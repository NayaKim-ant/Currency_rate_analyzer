from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ArticleSearchResult(BaseModel):
    article_id: int
    source: str
    title: str
    summary: str | None
    url: str
    published_at: datetime | None
    relevance_score: Decimal
    matched_keywords: list[str]
    policy_keywords: list[str]
