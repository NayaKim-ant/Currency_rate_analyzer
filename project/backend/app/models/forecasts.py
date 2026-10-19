from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Float, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NewsFact(Base):
    __tablename__ = "news_facts"
    __table_args__ = (UniqueConstraint("article_id", "evidence_hash", name="uq_news_facts_evidence"),
                      Index("ix_news_facts_available", "available_at"))

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


class ForecastRun(Base):
    __tablename__ = "forecast_runs"
    __table_args__ = (Index("ix_forecast_runs_currency_created", "target_currency", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    target_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ForecastOutcome(Base):
    __tablename__ = "forecast_outcomes"
    __table_args__ = (UniqueConstraint("forecast_run_id", "horizon", name="uq_forecast_outcomes_run_horizon"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    forecast_run_id: Mapped[int] = mapped_column(ForeignKey("forecast_runs.id"), nullable=False)
    horizon: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    actual_cost: Mapped[float] = mapped_column(Float, nullable=False)
    eligible: Mapped[bool] = mapped_column(nullable=False)
    reason: Mapped[str] = mapped_column(String(120), nullable=False)
    candidate_errors: Mapped[dict] = mapped_column(JSON, nullable=False)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
