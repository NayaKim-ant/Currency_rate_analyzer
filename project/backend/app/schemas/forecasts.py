from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict


class NewsHintResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    factor: str
    currencies: list[str]
    direction: str
    claim_type: str
    figures: list[dict[str, Any]]
    event: dict[str, Any] | None = None
    evidence: str
    source_title: str
    source_url: str
    published_at: datetime | None = None
    available_at: datetime


class PurchaseOutlookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    signal: str
    title: str
    reason: str
    estimated_date: str
    date_is_estimate: bool = True


class ForecastResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    target_currency: str
    selected_horizon: int
    outlook: dict[str, Any] = {}
    run_id: int | None = None
    created_at: datetime | None = None
    forecast: dict[str, Any] | None = None
    stale: bool = False
    hints: list[NewsHintResponse] = []
    recent_factor_count: int = 0
    extractor: str
    scorecard: dict[str, Any] = {}
