from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict


class MarketEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    base_currency: str | None = None
    target_currency: str | None = None
    event_type: str
    title: str
    description: str | None = None
    occurred_at: datetime
    article_id: int | None = None
    confidence: Decimal | None = None
