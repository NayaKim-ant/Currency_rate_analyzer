import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.alerts import router as alerts_router
from app.api.v1.articles import router as articles_router
from app.api.v1.events import router as events_router
from app.api.v1.rates import router as rates_router
from app.api.v1.trends import router as trends_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.forecasts import router as forecasts_router
from app.core.config import settings
from app.services.scheduler import create_scheduler, sync_startup_history

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    scheduler = create_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    scheduler.add_job(
        sync_startup_history,
        trigger="date",
        id="startup-data-catchup",
        name="Catch up market data on startup",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=86400,
    )

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Market Analysis API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)
app.include_router(rates_router, prefix="/api/v1")
app.include_router(trends_router, prefix="/api/v1")
app.include_router(alerts_router, prefix="/api/v1")
app.include_router(articles_router, prefix="/api/v1")
app.include_router(events_router, prefix="/api/v1")
app.include_router(jobs_router, prefix="/api/v1")
app.include_router(forecasts_router, prefix="/api/v1")


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
