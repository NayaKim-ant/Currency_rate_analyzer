from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.jobs import AnalysisJob, JobTransition
from app.services import job_runner
from app.services.job_runner import advance, drain_jobs, worker_guard
from app.services.jobs import JobConflict, JobState, claim_job, enqueue_job, transition, utcnow


@pytest.fixture
def factory(test_database):
    return sessionmaker(bind=test_database, autoflush=False, expire_on_commit=False)


@pytest.fixture
def successful_pipeline(monkeypatch):
    calls = []

    def collect(job_type, factory):
        calls.append("collect")
        with factory() as session:
            assert session.scalar(select(AnalysisJob.state).where(AnalysisJob.active_key == job_type)) == "COLLECTING"
        return {"rates": 8}

    def analyze(session, include_alerts=True):
        assert include_alerts is False
        calls.append("analyze")
        return {"snapshots": 8, "events_created": 0, "alerts_created": 0}

    def alerts(session):
        calls.append("alerts")
        return 1

    monkeypatch.setattr(job_runner, "collect_inputs", collect)
    monkeypatch.setattr(job_runner, "analyze_market", analyze)
    monkeypatch.setattr(job_runner, "evaluate_alert_rules", alerts)
    return calls


def test_pipeline_persists_every_legal_stage_and_results(factory, successful_pipeline):
    with factory() as session:
        job_id = enqueue_job(session, "rates").id
    assert drain_jobs(factory=factory) == 1
    with factory() as session:
        job = session.get(AnalysisJob, job_id)
        assert job.state == "COMPLETED"
        assert job.attempts == 1
        assert job.active_key is None and job.attempt_token is None
        assert job.result == {"rates": 8, "snapshots": 8, "events_created": 0, "alerts_created": 1}
        history = list(session.scalars(select(JobTransition).where(JobTransition.job_id == job_id).order_by(JobTransition.id)))
        assert [row.to_state for row in history] == ["QUEUED", "COLLECTING", "ANALYZING", "EVALUATING_ALERTS", "COMPLETED"]
        with pytest.raises(JobConflict, match="Cannot move"):
            transition(session, job, JobState.COLLECTING)
    assert successful_pipeline == ["collect", "analyze", "alerts"]


def test_analysis_only_job_skips_collection(factory, successful_pipeline):
    with factory() as session:
        enqueue_job(session, "analysis")
    assert drain_jobs(factory=factory) == 1
    assert successful_pipeline == ["analyze", "alerts"]


def test_collection_job_cannot_skip_its_collection_stage(factory):
    with factory() as session:
        job = enqueue_job(session, "rates")
        with pytest.raises(JobConflict, match="must start with COLLECTING"):
            transition(session, job, JobState.ANALYZING)
        assert job.state == "QUEUED"


def test_failed_jobs_back_off_and_stop_after_three_attempts(factory, monkeypatch):
    def fail(*args):
        raise OSError("provider unavailable")

    monkeypatch.setattr(job_runner, "collect_inputs", fail)
    with factory() as session:
        job_id = enqueue_job(session, "rates").id
    for attempt in range(1, 4):
        assert drain_jobs(factory=factory) == 1
        with factory() as session:
            job = session.get(AnalysisJob, job_id)
            assert job.state == "FAILED" and job.attempts == attempt
            assert "provider unavailable" in job.error
            if attempt < 3:
                assert job.active_key == "rates" and job.available_at is not None
                assert drain_jobs(factory=factory) == 0  # Backoff has not elapsed.
                job.available_at = utcnow() - timedelta(seconds=1)
                session.commit()
            else:
                assert job.active_key is None and job.available_at is None
    assert drain_jobs(factory=factory) == 0


def test_interrupted_attempt_is_recovered_after_worker_lock_released(factory, successful_pipeline):
    with factory() as session:
        job_id = enqueue_job(session, "rates").id
        old_token = claim_job(session).attempt_token
    # Database retains COLLECTING; a new worker proves the old owner is gone.
    assert drain_jobs(factory=factory) == 1
    with factory() as session:
        job = session.get(AnalysisJob, job_id)
        assert job.state == "COMPLETED" and job.attempts == 2
        history = list(session.scalars(select(JobTransition).where(JobTransition.job_id == job_id).order_by(JobTransition.id)))
        assert [row.to_state for row in history[:4]] == ["QUEUED", "COLLECTING", "FAILED", "QUEUED"]
        assert "interrupted" in history[2].message
    with pytest.raises(JobConflict, match="no longer owns"):
        advance(factory, job_id, old_token, JobState.ANALYZING, {})


def test_second_worker_cannot_claim_or_recover_active_work(factory, successful_pipeline):
    with factory() as session:
        job_id = enqueue_job(session, "rates").id
    with worker_guard(factory) as acquired:
        assert acquired is True
        assert drain_jobs(factory=factory) == 0
    with factory() as session:
        assert session.get(AnalysisJob, job_id).state == "QUEUED"
    assert drain_jobs(factory=factory) == 1


def test_api_deduplicates_requests_and_exposes_history(client, factory):
    first = client.post("/api/v1/jobs/collection", json={"job_type": "rates"})
    second = client.post("/api/v1/jobs/collection", json={"job_type": "rates"})
    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["state"] == "QUEUED"
    detail = client.get(f"/api/v1/jobs/{first.json()['id']}").json()
    assert detail["history"][0]["to_state"] == "QUEUED"
    assert len(client.get("/api/v1/jobs").json()) == 1
    assert client.post(f"/api/v1/jobs/{first.json()['id']}/retry").status_code == 409
    assert client.get("/api/v1/jobs/999").status_code == 404
    assert client.post("/api/v1/jobs/999/retry").status_code == 404
    assert client.post("/api/v1/jobs/collection", json={"job_type": "unknown"}).status_code == 422


def test_exhausted_job_can_be_retried_manually_without_losing_history(client, factory, monkeypatch, successful_pipeline):
    with factory() as session:
        job = enqueue_job(session, "rates")
        job.max_attempts = 1
        session.commit()
        job_id = job.id
    original = job_runner.collect_inputs

    def fail(*args):
        raise ValueError("bad provider payload")

    monkeypatch.setattr(job_runner, "collect_inputs", fail)
    drain_jobs(factory=factory)
    response = client.post(f"/api/v1/jobs/{job_id}/retry")
    assert response.status_code == 202 and response.json()["max_attempts"] == 2
    monkeypatch.setattr(job_runner, "collect_inputs", original)
    drain_jobs(factory=factory)
    detail = client.get(f"/api/v1/jobs/{job_id}").json()
    assert detail["state"] == "COMPLETED" and detail["attempts"] == 2
    assert any("bad provider payload" in (row["message"] or "") for row in detail["history"])


def test_separate_worker_mode_queues_startup_work_without_executing_it(factory, monkeypatch):
    from app.core.config import settings
    from app.services import scheduler

    monkeypatch.setattr(settings, "job_worker_enabled", False)
    monkeypatch.setattr(scheduler, "SessionLocal", factory)

    def unexpected_drain():
        raise AssertionError("API must not execute jobs in separate-worker mode")

    monkeypatch.setattr(scheduler, "drain_jobs", unexpected_drain)
    scheduler.sync_startup_history()
    scheduler.sync_rate_history()  # Reuses startup's queued rates job.
    with factory() as session:
        jobs = list(session.scalars(select(AnalysisJob)))
        assert len(jobs) == 3
        assert {job.state for job in jobs} == {"QUEUED"}
    assert "pipeline-worker" not in {job.id for job in scheduler.create_scheduler().get_jobs()}
