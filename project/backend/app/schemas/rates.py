from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class RatePoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rate_date: date
    rate: Decimal
    ma_5: Decimal | None
    ma_20: Decimal | None
    ma_60: Decimal | None


class RateSeriesResponse(BaseModel):
    base_currency: str
    target_currency: str
    requested_days: int
    points: list[RatePoint]
    trend_state: str
    quote_direction: Literal["target_per_base", "base_per_target"] = "target_per_base"
    rate_currency: str
    unit_currency: str
