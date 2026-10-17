from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.core.currencies import HOME_CURRENCY


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    __table_args__ = (
        UniqueConstraint("base_currency", "target_currency", "rate_date", name="uq_exchange_rates_pair_date"),
        Index("ix_exchange_rates_pair_date", "base_currency", "target_currency", "rate_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    target_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rate_date: Mapped[date] = mapped_column(Date, nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="frankfurter")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


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


class TrendSnapshot(Base):
    __tablename__ = "trend_snapshots"
    __table_args__ = (
        UniqueConstraint("base_currency", "target_currency", "as_of_date", name="uq_trend_snapshots_pair_date"),
        Index("ix_trend_snapshots_pair_date", "base_currency", "target_currency", "as_of_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    target_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    ma_5: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    ma_20: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    ma_60: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    trend_state: Mapped[str] = mapped_column(String(24), nullable=False)
    signal_strength: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    daily_change_percent: Mapped[Decimal | None] = mapped_column(Numeric(10, 5))
    change_point: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class MarketEvent(Base):
    __tablename__ = "market_events"
    __table_args__ = (Index("ix_market_events_currency_time", "target_currency", "occurred_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    base_currency: Mapped[str | None] = mapped_column(String(3))
    target_currency: Mapped[str | None] = mapped_column(String(3))
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    article_id: Mapped[int | None] = mapped_column(ForeignKey("articles.id", ondelete="SET NULL"))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False, default=HOME_CURRENCY)
    target_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(48), nullable=False)
    threshold: Mapped[Decimal] = mapped_column(Numeric(12, 5), nullable=False)
    lookback_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AlertEvent(Base):
    __tablename__ = "alert_events"
    __table_args__ = (Index("ix_alert_events_currency_fired_at", "target_currency", "fired_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("alert_rules.id", ondelete="SET NULL"))
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    target_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(48), nullable=False)
    measured_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
