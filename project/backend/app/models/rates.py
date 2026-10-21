from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
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
