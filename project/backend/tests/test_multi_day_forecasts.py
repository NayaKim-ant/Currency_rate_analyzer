from copy import deepcopy
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.forecasts import ForecastOutcome
from app.services.forecasting.scorecard import settle_forecasts, scorecard
from app.services.forecasting.outlook import estimated_quote_date, timing_signal
from tests.test_forecast_scorecard import run, quote, payload

UTC = timezone.utc


def test_multi_horizon_outcomes_wait_for_nth_quote_and_stay_separate(test_database):
    with Session(test_database) as s:
        r = run(s, datetime(2026, 1, 3, 8, tzinfo=UTC))
        r.payload = {**r.payload, "horizon_forecasts": {str(h): payload() for h in (1, 3, 5, 10)}}
        s.commit()
        quote(s)
        assert settle_forecasts(s, datetime(2026, 1, 6, tzinfo=UTC)) == 1
        assert s.scalar(select(ForecastOutcome.horizon)) == 1
        quote(s, date(2026, 1, 6), 1420)
        quote(s, date(2026, 1, 7), 1430)
        assert settle_forecasts(s, datetime(2026, 1, 8, tzinfo=UTC)) == 1
        assert settle_forecasts(s, datetime(2026, 1, 9, tzinfo=UTC)) == 0
        o = s.scalar(select(ForecastOutcome).where(ForecastOutcome.horizon == 3))
        assert o.target_date == date(2026, 1, 7) and o.actual_cost == pytest.approx(1430, abs=.001)
        assert scorecard(s, "USD", horizon=1)["distinct_outcomes"] == 1
        assert scorecard(s, "USD", horizon=3)["distinct_outcomes"] == 1
        assert scorecard(s, "USD", horizon=5)["distinct_outcomes"] == 0


def test_late_long_horizon_cannot_use_already_known_partial_return(test_database):
    with Session(test_database) as s:
        r = run(s, datetime(2026, 1, 6, 8, tzinfo=UTC))
        r.payload = {**r.payload, "horizon_forecasts": {"3": payload()}}
        s.commit()
        for i in range(3):
            quote(s, date(2026, 1, 5)+timedelta(days=i), 1410+i)
        assert settle_forecasts(s, datetime(2026, 1, 8, tzinfo=UTC)) == 1
        assert not s.scalar(select(ForecastOutcome.eligible))


@pytest.mark.parametrize("model,active,band,expected", [
    ("no_change", True, (1410, 1430), "no_edge"),
    ("ridge", False, (1410, 1430), "no_edge"),
    ("ridge", True, (1410, 1430), "buy_sooner"),
    ("ridge", True, (1350, 1380), "wait"),
    ("ridge", True, (1350, 1430), "no_edge"),
])
def test_timing_requires_forward_evidence_and_clear_error_range(model, active, band, expected):
    p = payload()
    p.update(model=model, forward_selection={"active": active})
    p["error_band"] = dict(lower=band[0], upper=band[1])
    result = timing_signal(p, date(2026, 1, 2), 5, datetime(2026, 1, 3, tzinfo=UTC))
    assert result["signal"] == expected
    assert result["estimated_date"] == "2026-01-09" and result["date_is_estimate"]
    assert timing_signal(p, date(2026, 1, 2), 5, datetime(2026, 1, 3, tzinfo=UTC), stale=True)["signal"] == "outdated"


def test_display_dates_skip_weekends_and_old_forecasts_do_not_give_timing_calls():
    assert estimated_quote_date(date(2026, 10, 16), 1) == date(2026, 10, 19)
    assert estimated_quote_date(date(2026, 10, 16), 10) == date(2026, 10, 30)
    assert timing_signal(payload(), date(2026, 1, 2), 5, datetime(2026, 2, 2, tzinfo=UTC))["signal"] == "outdated"


def test_api_accepts_horizons_and_rejects_unsupported_values(client):
    assert client.get("/api/v1/forecasts?horizon=5").status_code == 200
    assert client.get("/api/v1/forecasts?horizon=2").status_code == 422


@pytest.mark.parametrize("horizon", [3, 5, 10])
def test_direct_horizon_labels_purged_folds_and_heldout_isolation(horizon):
    np = pytest.importorskip("numpy")
    pytest.importorskip("torch")
    pytest.importorskip("sklearn")
    from app.services import forecasting
    from tests.test_forecasting import history
    rates, now = history(260)
    costs, features, origins, x, y = forecasting.build_dataset(rates, [], "USD", now, horizon)
    assert y[0] == pytest.approx(np.log(costs[origins[0]+horizon]/costs[origins[0]])*100)
    result = forecasting.train_pair(rates, [], "USD", now, epochs=1, horizon=horizon)
    assert set(result["candidate_forecasts"]) == {"no_change", "ridge", "boosted_trees"}
    assert all(f["last_training_target"] < f["first_origin"] for f in result["folds"])
    assert result["folds"][0]["last_evaluation_target"] <= result["folds"][1]["first_origin"]
    assert result["folds"][1]["last_evaluation_target"] <= result["folds"][2]["first_origin"]
    assert all(v["samples"] == 40 for v in result["validation"].values())
    assert all(v["samples"] == 20 for v in result["held_out_test"].values())
    rates[-1].rate *= 2
    changed = forecasting.train_pair(rates, [], "USD", now, epochs=1, horizon=horizon)
    assert changed["validation"] == result["validation"] and changed["model"] == result["model"]
    assert changed["held_out_test"]["no_change"] != result["held_out_test"]["no_change"]
