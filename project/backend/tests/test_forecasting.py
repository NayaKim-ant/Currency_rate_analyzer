from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("torch")
pytest.importorskip("sklearn")

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.jobs import AnalysisJob, JobTransition
from app.services.forecasting import engine as forecasting
from app.services.forecasting.engine import build_dataset, news_vector, train_pair
from app.services.pipeline.runner import drain_jobs
from app.services.pipeline.state_machine import enqueue_job


def fact(published, available, **changes):
    value = dict(published_at=published, available_at=available, superseded_at=None, factor="inflation",
                 currencies=["USD"], claim_type="reported", direction="increase", figures=[], evidence="US inflation rose to 3%.", evidence_hash="test")
    value.update(changes)
    return SimpleNamespace(**value)


def history(count=180):
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rates = []
    for i in range(count):
        cost = 1300 + i*0.3 + np.sin(i/4)*8
        rates.append(SimpleNamespace(rate_date=(start+timedelta(days=i)).date(), rate=Decimal(str(1/cost))))
    return rates, start+timedelta(days=count)


def test_news_features_never_use_future_backfills_or_superseded_versions():
    cutoff = datetime(2026, 10, 16, tzinfo=timezone.utc)
    old = fact(cutoff-timedelta(days=1), cutoff+timedelta(days=1))
    assert not any(news_vector([old], "USD", cutoff))
    current = fact(cutoff-timedelta(days=1), cutoff-timedelta(hours=1))
    assert any(news_vector([current], "USD", cutoff))
    assert news_vector([current, current], "USD", cutoff) == news_vector([current], "USD", cutoff)
    current.superseded_at = cutoff-timedelta(minutes=1)
    assert not any(news_vector([current], "USD", cutoff))
    assert any(news_vector([current], "USD", cutoff-timedelta(minutes=30)))
    assert not any(news_vector([fact(None, cutoff)], "USD", cutoff))
    expectation = fact(cutoff, cutoff, claim_type="forward_looking")
    values = np.array(news_vector([expectation], "USD", cutoff)).reshape(2, 6, forecasting.NEWS_CHANNELS)
    assert values[:, :, 0].sum() == 0 and values[:, :, 3].sum() > 0
    assert any(news_vector([fact(cutoff, cutoff, factor="risk", currencies=[])], "USD", cutoff))


def test_future_rate_changes_do_not_change_earlier_features():
    rates, now = history()
    original = build_dataset(rates, [], "USD", now)
    rates[-1].rate *= Decimal("0.8")
    changed = build_dataset(rates, [], "USD", now)
    np.testing.assert_array_equal(original[3], changed[3])  # Final quote is a target, not an earlier input.
    np.testing.assert_array_equal(original[4][:-1], changed[4][:-1])


def test_numeric_news_figures_are_model_inputs_not_just_keywords():
    cutoff = datetime(2026, 10, 16, tzinfo=timezone.utc)
    base = fact(cutoff-timedelta(hours=1), cutoff-timedelta(hours=1), factor="interest_rates",
                evidence="The Fed raised interest rates by 25 basis points.")
    without = news_vector([base], "USD", cutoff)
    base.figures = [{"text": "25 basis points", "value": 25, "unit": "basis points", "assigned": True}]
    with_numbers = news_vector([base], "USD", cutoff)
    assert without != with_numbers
    assert max(with_numbers) >= 0.25
    base.figures[0]["assigned"] = False
    assert news_vector([base], "USD", cutoff) == without


def test_lstm_runs_with_honest_news_gate_and_untouched_final_test():
    rates, now = history()
    result = train_pair(rates, [], "USD", now, epochs=2)
    assert result["configuration"] == {**forecasting.CONFIG, "horizon_observations": 1, "epochs": 2}
    assert result["status"] == "experimental"
    assert result["news"]["eligible"] is False
    assert "news_lstm" not in result["validation"]
    assert result["held_out_test"]["no_change"]["samples"] == 20
    assert result["error_band"]["lower"] <= result["forecast_cost"] <= result["error_band"]["upper"]
    rates[-1].rate *= Decimal("0.8")
    changed = train_pair(rates, [], "USD", now, epochs=2)
    assert changed["model"] == result["model"]
    assert changed["validation"] == result["validation"]
    assert changed["held_out_test"]["no_change"]["mae_krw"] != result["held_out_test"]["no_change"]["mae_krw"]


def test_news_augmented_lstm_really_trains_when_point_in_time_coverage_exists():
    rates, now = history()
    facts = [fact(datetime.combine(row.rate_date, datetime.min.time(), tzinfo=timezone.utc),
                  datetime.combine(row.rate_date, datetime.min.time(), tzinfo=timezone.utc),
                  evidence=f"US inflation report number {i}", evidence_hash=str(i),
                  direction="increase" if i % 2 else "decrease") for i, row in enumerate(rates)]
    result = train_pair(rates, facts, "USD", now, epochs=2)
    assert result["news"]["eligible"] is True
    assert "news_lstm" in result["validation"] and "news_lstm" in result["candidate_forecasts"]
    assert np.isfinite(result["news"]["sensitivity_krw"])
    assert len(result["news"]["factor_sensitivities"]) == 6


def test_forecast_job_has_persistent_extraction_and_training_states(test_database, monkeypatch):
    factory = sessionmaker(bind=test_database, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(forecasting, "train_forecasts", lambda session: 8)
    with factory() as session:
        job_id = enqueue_job(session, "forecast").id
    assert drain_jobs(factory=factory) == 1
    with factory() as session:
        job = session.get(AnalysisJob, job_id)
        assert job.state == "COMPLETED" and job.result["forecasts"] == 8
        states = list(session.scalars(select(JobTransition.to_state).where(JobTransition.job_id == job_id).order_by(JobTransition.id)))
        assert states == ["QUEUED", "EXTRACTING_HINTS", "FORECASTING", "COMPLETED"]
