from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class JobCreate(BaseModel):
    job_type: Literal["rates", "news_history", "news_recent", "analysis", "forecast"] = "rates"


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_type: str
    state: str
    source: str
    attempts: int
    max_attempts: int
    result: dict
    error: str | None
    created_at: datetime
    updated_at: datetime
    available_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None


class TransitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_state: str | None
    to_state: str
    attempt: int
    message: str | None
    created_at: datetime


class JobDetail(JobRead):
    history: list[TransitionRead]
