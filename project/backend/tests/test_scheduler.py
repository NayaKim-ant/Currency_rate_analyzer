from app.core.config import settings
from app.services.pipeline.scheduler import create_scheduler


def test_scheduler_runs_rate_and_news_jobs_daily_in_configured_timezone() -> None:
    scheduler = create_scheduler()
    jobs = {job.id: job for job in scheduler.get_jobs()}

    assert settings.rate_history_days == 365
    assert set(jobs) == {"daily-rate-history-sync", "daily-news-sync", "pipeline-worker"}
    assert str(jobs["daily-rate-history-sync"].trigger.timezone) == "Asia/Seoul"
    rate_fields = {field.name: str(field) for field in jobs["daily-rate-history-sync"].trigger.fields}
    news_fields = {field.name: str(field) for field in jobs["daily-news-sync"].trigger.fields}
    assert rate_fields["hour"] == str(settings.daily_sync_hour)
    assert rate_fields["minute"] == "0"
    assert news_fields["minute"] == "20"
