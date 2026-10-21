from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.pipeline.runner import drain_jobs
from app.services.pipeline.state_machine import enqueue_job


def submit_scheduled(job_type: str) -> int:
    with SessionLocal() as session:
        job_id = enqueue_job(session, job_type, source="schedule").id
    if settings.job_worker_enabled:
        drain_jobs()
    return job_id


def sync_rate_history() -> int:
    return submit_scheduled("rates")


def sync_recent_news() -> int:
    return submit_scheduled("news_recent")


def sync_news_history() -> int:
    return submit_scheduled("news_history")


def sync_startup_history() -> None:
    with SessionLocal() as session:
        for job_type in ("rates", "news_history", "news_recent"):
            enqueue_job(session, job_type, source="startup")
    if settings.job_worker_enabled:
        drain_jobs()


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=settings.scheduler_timezone)
    scheduler.add_job(sync_rate_history, trigger="cron", hour=settings.daily_sync_hour, minute=0,
                      id="daily-rate-history-sync", replace_existing=True, coalesce=True,
                      max_instances=1, misfire_grace_time=86400)
    scheduler.add_job(sync_recent_news, trigger="cron", hour=settings.daily_sync_hour, minute=20,
                      id="daily-news-sync", replace_existing=True, coalesce=True,
                      max_instances=1, misfire_grace_time=86400)
    if settings.job_worker_enabled:
        scheduler.add_job(drain_jobs, trigger="interval", seconds=5, id="pipeline-worker",
                          replace_existing=True, coalesce=True, max_instances=1, misfire_grace_time=60)
    return scheduler
