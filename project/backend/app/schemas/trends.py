from datetime import date
from decimal import Decimal
from pydantic import BaseModel, ConfigDict


class TrendSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    base_currency: str
    target_currency: str
    as_of_date: date
    trend_state: str
    ma_5: Decimal | None = None
    ma_20: Decimal | None = None
    ma_60: Decimal | None = None
    daily_change_percent: Decimal | None = None
    change_point: bool = False
    method: str = (
        "MA5 > MA20 > MA60: uptrend; MA5 < MA20 < MA60: downtrend; otherwise neutral. "
        "Incomplete windows: insufficient_data. Change point: absolute daily change >= 2%."
    )
