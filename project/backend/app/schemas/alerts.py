from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.currencies import FOREIGN_CURRENCIES, HOME_CURRENCY

AlertType = Literal[
    "rapid_rise",
    "rapid_fall",
    "trend_reversal_up",
    "trend_reversal_down",
    "policy_price_link",
    "change_point_candidate",
    "won_cost_at_or_below",
    "won_cost_at_or_above",
]


class AlertRuleCreate(BaseModel):
    base_currency: str = Field(default=HOME_CURRENCY, min_length=3, max_length=3, pattern="^[A-Za-z]{3}$")
    target_currency: str = Field(min_length=3, max_length=3, pattern="^[A-Za-z]{3}$")
    alert_type: AlertType
    threshold: Decimal = Field(gt=0, max_digits=12, decimal_places=5)
    lookback_days: int = Field(default=1, ge=1, le=365)

    @model_validator(mode="after")
    def validate_won_price_pair(self):
        if self.alert_type.startswith("won_cost_") and (
            self.base_currency.upper() != HOME_CURRENCY or self.target_currency.upper() not in FOREIGN_CURRENCIES
        ):
            raise ValueError("Won-cost alerts require KRW as base and a supported foreign target currency")
        return self


class AlertRuleUpdate(BaseModel):
    enabled: bool


class AlertRuleRead(AlertRuleCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    enabled: bool
    created_at: datetime
