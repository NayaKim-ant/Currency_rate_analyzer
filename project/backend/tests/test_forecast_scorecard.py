from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.forecasts import ForecastOutcome, ForecastRun
from app.models.market import ExchangeRate
from app.services.forecast_scorecard import apply_forward_selection, scorecard, settle_forecasts

UTC = timezone.utc


def payload(config="test-v1"):
    return {"status": "experimental", "model": "rates_lstm", "current_cost": 1390.,
            "forecast_cost": 1400., "candidate_forecasts": {"no_change": 1390., "rates_lstm": 1400.},
            "candidate_error_widths": {"no_change": 20., "rates_lstm": 15.},
            "configuration": {"version": config}, "validation": {
                "no_change": {"mae_krw": 12.}, "rates_lstm": {"mae_krw": 10.}},
            "news": {"eligible": False}, "error_band": {"lower": 1385., "upper": 1415.}}


def run(session, issued, origin=date(2026, 1, 2), config="test-v1"):
    row = ForecastRun(target_currency="USD", as_of_date=origin, created_at=issued, payload=payload(config))
    session.add(row)
    session.commit()
    return row


def quote(session, day=date(2026, 1, 5), cost=1410):
    row = ExchangeRate(base_currency="KRW", target_currency="USD", rate_date=day,
        rate=Decimal(1)/Decimal(cost), source="test", created_at=datetime.combine(day, datetime.min.time(), UTC)+timedelta(hours=17))
    session.add(row)
    session.commit()
    return row


def test_pending_weekend_outcome_errors_and_revision_idempotency(test_database):
    with Session(test_database) as s:
        r = run(s, datetime(2026, 1, 3, 8, tzinfo=UTC))
        saved = deepcopy(r.payload)
        assert settle_forecasts(s, datetime(2026, 1, 4, tzinfo=UTC)) == 0
        q = quote(s)
        assert settle_forecasts(s, datetime(2026, 1, 5, 12, tzinfo=UTC)) == 0  # Not collected yet.
        assert settle_forecasts(s, datetime(2026, 1, 6, tzinfo=UTC)) == 1
        outcome = s.scalar(select(ForecastOutcome))
        assert outcome.eligible and outcome.target_date == date(2026, 1, 5)
        assert outcome.candidate_errors["rates_lstm"]["absolute_error"] == pytest.approx(10, abs=.001)
        assert outcome.candidate_errors["rates_lstm"]["signed_error"] == pytest.approx(-10, abs=.001)
        q.rate = Decimal(1)/Decimal(1500)
        s.commit()
        assert settle_forecasts(s, datetime(2026, 1, 7, tzinfo=UTC)) == 0
        s.refresh(r)
        assert r.payload == saved
        assert outcome.actual_cost == pytest.approx(1410, abs=.001)


def test_same_day_and_backdated_quotes_are_not_forward_evidence(test_database):
    with Session(test_database) as s:
        run(s, datetime(2026, 1, 5, 8, tzinfo=UTC))
        run(s, datetime(2026, 2, 1, tzinfo=UTC))
        quote(s)
        assert settle_forecasts(s, datetime(2026, 2, 2, tzinfo=UTC)) == 2
        assert all(not o.eligible for o in s.scalars(select(ForecastOutcome)))
        assert scorecard(s, "USD")["distinct_outcomes"] == 0


def test_scores_deduplicate_target_dates_filter_versions_and_cutoffs(test_database):
    with Session(test_database) as s:
        run(s, datetime(2026, 1, 3, 8, tzinfo=UTC))
        latest = run(s, datetime(2026, 1, 4, 8, tzinfo=UTC))
        run(s, datetime(2026, 1, 4, 9, tzinfo=UTC), config="other")
        quote(s)
        settle_forecasts(s, datetime(2026, 1, 6, tzinfo=UTC))
        evidence = scorecard(s, "USD", datetime(2026, 1, 7, tzinfo=UTC), {"version": "test-v1"})
        assert evidence["distinct_outcomes"] == 1
        assert evidence["candidates"]["rates_lstm"]["samples"] == 1
        assert evidence["recent"][0]["forecast_run_id"] == latest.id
        assert scorecard(s, "USD", datetime(2026, 1, 5, tzinfo=UTC))["distinct_outcomes"] == 0


def evidence(n, model_error=8.):
    return {"distinct_outcomes": n, "candidates": {
        "no_change": {"samples": n, "mae_krw": 10., "baseline_mae_krw": 10.},
        "rates_lstm": {"samples": n, "mae_krw": model_error, "baseline_mae_krw": 10.}}}


def test_forward_errors_gate_future_selection_without_reusing_holdout():
    p = payload()
    apply_forward_selection(p, evidence(29, model_error=20))
    assert p["model"] == "rates_lstm" and not p["forward_selection"]["active"]
    p = payload()
    apply_forward_selection(p, evidence(30, model_error=20))
    assert p["model"] == "no_change" and p["forecast_cost"] == 1390
    assert p["error_band"] == {"lower": 1370., "upper": 1410.}
    p = payload()
    p["model"] = "no_change"
    apply_forward_selection(p, evidence(30, model_error=8))
    assert p["model"] == "rates_lstm" and p["forecast_cost"] == 1400
    p = payload()
    p["validation"]["rates_lstm"]["mae_krw"] = 20
    apply_forward_selection(p, evidence(30, model_error=8))
    assert p["model"] == "no_change"  # Cannot bypass original validation rule.


def test_news_requires_matched_forward_comparison_and_historical_eligibility():
    p = payload()
    p["candidate_forecasts"]["news_lstm"] = 1405
    p["candidate_error_widths"]["news_lstm"] = 12
    p["validation"]["news_lstm"] = {"mae_krw": 8}
    p["news"]["eligible"] = True
    e = evidence(30)
    e["candidates"]["news_lstm"] = {"samples": 30, "mae_krw": 6, "baseline_mae_krw": 10}
    e["news_vs_rates"] = {"samples": 29, "news_mae": 6, "rates_mae": 8}
    apply_forward_selection(p, e)
    assert p["model"] == "rates_lstm"
    e["news_vs_rates"]["samples"] = 30
    apply_forward_selection(p, e)
    assert p["model"] == "news_lstm"
    p["news"]["eligible"] = False
    apply_forward_selection(p, e)
    assert p["model"] == "rates_lstm"
