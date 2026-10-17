"""Persisted job states and legal transitions. Network work lives in job_runner."""

from datetime import datetime, timedelta, timezone
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.jobs import AnalysisJob, JobTransition

JOB_TYPES = ("rates", "news_history", "news_recent", "analysis", "forecast")
QUEUE_LOCK = 7314126502


class JobState(StrEnum):
    EXTRACTING_HINTS = "EXTRACTING_HINTS"
    FORECASTING = "FORECASTING"
    QUEUED = "QUEUED"
    COLLECTING = "COLLECTING"
    ANALYZING = "ANALYZING"
    EVALUATING_ALERTS = "EVALUATING_ALERTS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


RUNNING_STATES = (JobState.COLLECTING, JobState.ANALYZING, JobState.EVALUATING_ALERTS, JobState.EXTRACTING_HINTS, JobState.FORECASTING)
TRANSITIONS = {
    JobState.QUEUED: {JobState.COLLECTING, JobState.ANALYZING, JobState.EXTRACTING_HINTS},
    JobState.EXTRACTING_HINTS: {JobState.FORECASTING, JobState.FAILED},
    JobState.FORECASTING: {JobState.COMPLETED, JobState.FAILED},
    JobState.COLLECTING: {JobState.ANALYZING, JobState.FAILED},
    JobState.ANALYZING: {JobState.EVALUATING_ALERTS, JobState.FAILED},
    JobState.EVALUATING_ALERTS: {JobState.COMPLETED, JobState.FAILED},
    JobState.FAILED: {JobState.QUEUED},
    JobState.COMPLETED: set(),
}


class JobConflict(ValueError):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def lock_queue(session: Session) -> None:
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text(f"SELECT pg_advisory_xact_lock({QUEUE_LOCK})"))


def transition(session: Session, job: AnalysisJob, next_state: JobState, message: str | None = None) -> None:
    if next_state not in TRANSITIONS[JobState(job.state)]:
        raise JobConflict(f"Cannot move job from {job.state} to {next_state}")
    if job.state == JobState.QUEUED:
        first_stage = JobState.EXTRACTING_HINTS if job.job_type == "forecast" else JobState.ANALYZING if job.job_type == "analysis" else JobState.COLLECTING
        if next_state != first_stage:
            raise JobConflict(f"A {job.job_type} job must start with {first_stage}")
    session.add(JobTransition(job_id=job.id, from_state=job.state, to_state=next_state,
                              attempt=job.attempts, message=message))
    job.state = next_state
    job.updated_at = utcnow()


def enqueue_job(session: Session, job_type: str, source: str = "manual") -> AnalysisJob:
    if job_type not in JOB_TYPES:
        raise ValueError("Unsupported job type")
    lock_queue(session)
    existing = session.scalar(select(AnalysisJob).where(AnalysisJob.active_key == job_type))
    if existing is not None:
        session.commit()
        return existing
    job = AnalysisJob(job_type=job_type, state=JobState.QUEUED, source=source, active_key=job_type,
                      attempts=0, max_attempts=3, available_at=utcnow(), result={})
    session.add(job)
    session.flush()
    session.add(JobTransition(job_id=job.id, from_state=None, to_state=JobState.QUEUED, attempt=0,
                              message=f"Requested by {source}"))
    session.commit()
    session.refresh(job)
    return job


def retry_job(session: Session, job_id: int) -> AnalysisJob:
    lock_queue(session)
    job = session.scalar(select(AnalysisJob).where(AnalysisJob.id == job_id).with_for_update())
    if job is None:
        raise LookupError("Job not found")
    if job.state != JobState.FAILED:
        raise JobConflict("Only failed jobs can be retried")
    other = session.scalar(select(AnalysisJob.id).where(AnalysisJob.active_key == job.job_type, AnalysisJob.id != job.id))
    if other is not None:
        raise JobConflict("Another job of this type is already pending or running")
    transition(session, job, JobState.QUEUED, "Retry requested by user")
    job.active_key = job.job_type
    job.available_at = utcnow()
    job.finished_at = None
    job.max_attempts = max(job.max_attempts, job.attempts + 1)
    session.commit()
    return job


def mark_failed(session: Session, job: AnalysisJob, error: str, interrupted: bool = False) -> None:
    transition(session, job, JobState.FAILED, error)
    job.error = error[:2000]
    job.finished_at = utcnow()
    job.attempt_token = None
    if job.attempts < job.max_attempts:
        delay = 0 if interrupted else 30 * (2 ** (job.attempts - 1))
        job.available_at = utcnow() + timedelta(seconds=delay)
    else:
        job.active_key = None
        job.available_at = None


def recover_and_requeue(session: Session) -> None:
    """Caller MUST hold the exclusive worker lock, proving no worker is active."""
    lock_queue(session)
    for job in session.scalars(select(AnalysisJob).where(AnalysisJob.state.in_(RUNNING_STATES))):
        mark_failed(session, job, "Worker interrupted before this attempt completed; recovered from persisted state.", interrupted=True)
    session.flush()
    for job in session.scalars(select(AnalysisJob).where(
        AnalysisJob.state == JobState.FAILED, AnalysisJob.attempts < AnalysisJob.max_attempts,
        AnalysisJob.available_at <= utcnow(),
    )):
        transition(session, job, JobState.QUEUED, "Automatic retry")
        job.finished_at = None
    session.commit()


def claim_job(session: Session) -> AnalysisJob | None:
    job = session.scalar(select(AnalysisJob).where(
        AnalysisJob.state == JobState.QUEUED, AnalysisJob.available_at <= utcnow(),
    ).order_by(AnalysisJob.created_at, AnalysisJob.id).with_for_update(skip_locked=True).limit(1))
    if job is None:
        return None
    job.attempts += 1
    job.attempt_token = str(uuid4())
    job.started_at = utcnow()
    job.finished_at = None
    job.error = None
    job.result = {}
    transition(session, job, JobState.EXTRACTING_HINTS if job.job_type == "forecast" else JobState.ANALYZING if job.job_type == "analysis" else JobState.COLLECTING)
    session.commit()
    session.refresh(job)
    return job
