"""Run durable pipeline jobs with one exclusive PostgreSQL worker at a time."""

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from threading import Lock

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.jobs import AnalysisJob
from app.services.alert_engine import evaluate_alert_rules
from app.services.analysis import analyze_market
from app.services.collection import collect_recent_rates
from app.services.jobs import JobConflict, JobState, claim_job, mark_failed, recover_and_requeue, transition, utcnow
from app.services.news import fetch_news_history, iter_news_history_batches, store_news_articles

logger = logging.getLogger(__name__)
WORKER_LOCK = 7314126503
_local_worker_lock = Lock()
SessionFactory = Callable[[], Session]


@contextmanager
def worker_guard(factory: SessionFactory) -> Iterator[bool]:
    with factory() as session:
        engine = session.get_bind()
    if engine.dialect.name != "postgresql":
        acquired = _local_worker_lock.acquire(blocking=False)
        try:
            yield acquired
        finally:
            if acquired:
                _local_worker_lock.release()
        return
    # A dedicated connection keeps a session advisory lock across stage commits.
    # PostgreSQL releases it when a crashed process loses its connection.
    with engine.connect() as connection:
        acquired = connection.scalar(text(f"SELECT pg_try_advisory_lock({WORKER_LOCK})"))
        connection.commit()
        try:
            yield bool(acquired)
        finally:
            if acquired:
                connection.execute(text(f"SELECT pg_advisory_unlock({WORKER_LOCK})"))
                connection.commit()


def collect_inputs(job_type: str, factory: SessionFactory) -> dict[str, int]:
    if job_type == "rates":
        with factory() as session:
            return {"rates": collect_recent_rates(session, days=settings.rate_history_days)}
    if job_type == "news_recent":
        articles = fetch_news_history(days=7, include_body=True)
        with factory() as session:
            return {"articles": store_news_articles(session, articles)}
    count = 0
    for batch in iter_news_history_batches(days=settings.news_history_days, include_body=False):
        if batch:
            with factory() as session:
                count += store_news_articles(session, batch)
    return {"articles": count}


def owned_job(session: Session, job_id: int, token: str) -> AnalysisJob:
    job = session.scalar(select(AnalysisJob).where(AnalysisJob.id == job_id).with_for_update())
    if job is None or job.attempt_token != token:
        raise JobConflict("This attempt no longer owns the job")
    return job


def advance(factory: SessionFactory, job_id: int, token: str, state: JobState, result: dict) -> None:
    with factory() as session:
        job = owned_job(session, job_id, token)
        transition(session, job, state)
        job.result = result
        if state == JobState.COMPLETED:
            job.finished_at = utcnow()
            job.available_at = None
            job.active_key = None
            job.attempt_token = None
        session.commit()


def execute_job(job: AnalysisJob, factory: SessionFactory) -> None:
    job_id, token, job_type = job.id, job.attempt_token, job.job_type
    result = {}
    try:
        if job_type == "forecast":
            from app.services.news_facts import extract_news_facts
            with factory() as session:
                result["news_facts"] = extract_news_facts(session)
            advance(factory, job_id, token, JobState.FORECASTING, result.copy())
            try:
                from app.services.forecasting import train_forecasts
            except ImportError as error:
                raise RuntimeError("Install requirements-ml.txt in the backend virtual environment to run local forecasts") from error
            with factory() as session:
                result["forecasts"] = train_forecasts(session)
            advance(factory, job_id, token, JobState.COMPLETED, result.copy())
            return
        if job_type != "analysis":
            result.update(collect_inputs(job_type, factory))
            advance(factory, job_id, token, JobState.ANALYZING, result.copy())
        if job_type in ("rates", "analysis"):
            from app.services.forecast_scorecard import settle_forecasts
            with factory() as session:
                result["forecasts_scored"] = settle_forecasts(session)
        with factory() as session:
            if job_type.startswith("news"):
                from app.services.news_facts import extract_news_facts
                result["news_facts"] = extract_news_facts(session)
            result.update(analyze_market(session, include_alerts=False))
        advance(factory, job_id, token, JobState.EVALUATING_ALERTS, result.copy())
        with factory() as session:
            result["alerts_created"] = evaluate_alert_rules(session)
        advance(factory, job_id, token, JobState.COMPLETED, result.copy())
        if job_type in ("rates", "news_recent"):
            from app.models.forecasts import ForecastRun
            from app.services.jobs import enqueue_job
            with factory() as session:
                if session.scalar(select(ForecastRun.id).limit(1)) is not None:
                    enqueue_job(session, "forecast", source="schedule")
    except Exception as error:
        logger.exception("Pipeline job %s failed", job_id)
        with factory() as session:
            try:
                current = owned_job(session, job_id, token)
            except JobConflict:
                return  # A recovered attempt owns this job; do not overwrite it.
            mark_failed(session, current, f"{type(error).__name__}: {error}"[:2000])
            session.commit()


def drain_jobs(max_jobs: int = 20, factory: SessionFactory = SessionLocal) -> int:
    with worker_guard(factory) as acquired:
        if not acquired:
            return 0
        with factory() as session:
            recover_and_requeue(session)
        processed = 0
        for _ in range(max_jobs):
            with factory() as session:
                job = claim_job(session)
                if job is None:
                    break
                # Copy attributes before closing even if expire_on_commit is on.
                session.expunge(job)
            execute_job(job, factory)
            processed += 1
        return processed
