from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (Index("ix_articles_published_at", "published_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ArticleKeyword(Base):
    __tablename__ = "article_keywords"
    __table_args__ = (
        UniqueConstraint("article_id", "keyword", "category", name="uq_article_keywords_article_keyword_category"),
        Index("ix_article_keywords_category_keyword", "category", "keyword"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), nullable=False)
    keyword: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="general")
    weight: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False, default=Decimal("1"))


class ArticleRelevance(Base):
    __tablename__ = "article_relevance"
    __table_args__ = (
        UniqueConstraint("article_id", "base_currency", "target_currency", name="uq_article_relevance_article_pair"),
        Index("ix_article_relevance_pair_score", "base_currency", "target_currency", "score"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    target_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    matched_keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    rationale: Mapped[str | None] = mapped_column(Text)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class NewsFact(Base):
    __tablename__ = "news_facts"
    __table_args__ = (
        UniqueConstraint("article_id", "evidence_hash", name="uq_news_facts_evidence"),
        Index("ix_news_facts_available", "available_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    factor: Mapped[str] = mapped_column(String(32), nullable=False)
    currencies: Mapped[list] = mapped_column(JSON, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    claim_type: Mapped[str] = mapped_column(String(24), nullable=False)
    figures: Mapped[list] = mapped_column(JSON, nullable=False)
    event: Mapped[dict | None] = mapped_column(JSON)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    source_title: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extractor_version: Mapped[str] = mapped_column(String(32), nullable=False)
