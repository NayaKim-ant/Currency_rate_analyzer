from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.forecasts import ForecastOutcome, ForecastRun
from app.services.forecasting.leaderboard import build_leaderboard, gain
from app.services.forecasting.scorecard import scorecard


def snapshot():
    return {"model": "no_change", "configuration": {"version": "test"}, "news": {"eligible": False},
        "candidate_forecasts": {"no_change": 1400, "ridge": 1401, "boosted_trees": 1402, "rates_lstm": 1403},
        "validation": {"no_change": {"mae_krw": 10, "samples": 40}, "ridge": {"mae_krw": 8, "samples": 40},
                       "boosted_trees": {"mae_krw": 9, "samples": 40}, "rates_lstm": {"mae_krw": 11, "samples": 40}},
        "held_out_test": {"rates_lstm": {"mae_krw": 0}}}


def test_rankings_separate_forward_validation_selection_and_heldout():
    live = {name: {"mae_krw": error, "baseline_mae_krw": 10, "samples": 31}
            for name, error in {"no_change": 10, "ridge": 7, "boosted_trees": 5, "rates_lstm": 4}.items()}
    board = build_leaderboard(snapshot(), {"minimum_outcomes": 30,
        "comparison": {"samples": 31, "candidates": live}}, 5)
    rows = {r["model"]: r for r in board["rows"]}
    assert board["selected_model"] == "no_change"
    assert board["validation_leaders"] == ["ridge"]
    assert board["forward_leaders"] == ["rates_lstm"]
    assert rows["rates_lstm"]["status"] == "validation_gate"
    assert rows["ridge"]["status"] == "eligible"
    assert rows["boosted_trees"]["forward_gain_percent"] == 50
    assert rows["news_lstm"]["status"] == "not_supported"
    assert rows["rates_lstm"]["held_out_mae"] == 0  # Diagnostic, never ranking input.


def test_warmup_absent_candidates_and_zero_baseline_are_honest():
    p = snapshot()
    p["validation"].pop("rates_lstm")
    board = build_leaderboard(p, {}, 10)
    rows = {r["model"]: r for r in board["rows"]}
    assert not board["forward_ready"] and not board["history"] and not board["forward_leaders"]
    assert rows["ridge"]["forward_mae"] is None and rows["ridge"]["status"] == "collecting"
    assert rows["rates_lstm"]["status"] == "needs_training"
    assert rows["rates_lstm"]["validation_rank"] is None
    assert gain(0, 0) is None
    assert build_leaderboard(None, {}, 1)["selected_model"] is None


def test_ties_share_rank_and_early_forward_leaders_are_provisional():
    p = snapshot()
    p["validation"]["no_change"]["mae_krw"] = 8
    live = {n: {"mae_krw": 2, "baseline_mae_krw": 2, "samples": 1} for n in p["validation"]}
    b = build_leaderboard(p, {"comparison": {"samples": 1, "candidates": live}}, 3)
    assert b["validation_leaders"] == ["no_change", "ridge"]
    assert all(r["forward_rank"] == 1 for r in b["rows"] if r["model"] != "news_lstm")
    assert not b["forward_ready"]


def test_common_cohort_and_cumulative_history_ignore_missing_future_and_other_configs(test_database):
    utc = timezone.utc
    with Session(test_database) as s:
        def add(i, errors, config="current", eligible=True, horizon=5):
            target = date(2026, 1, 5)+timedelta(days=i)
            payload = snapshot()
            payload["configuration"] = {"version": config}
            run = ForecastRun(target_currency="USD", as_of_date=date(2026, 1, 2),
                created_at=datetime(2026, 1, 3, tzinfo=utc), payload={**payload, "horizon_forecasts": {"5": payload}})
            s.add(run); s.flush()
            s.add(ForecastOutcome(forecast_run_id=run.id, horizon=horizon, target_date=target,
                actual_cost=1400, eligible=eligible, reason="test",
                candidate_errors={n: {"absolute_error": e} for n, e in errors.items()},
                scored_at=datetime.combine(target, datetime.min.time(), utc)+timedelta(hours=20)))
        add(0, {"no_change": 10, "ridge": 8, "boosted_trees": 6, "rates_lstm": 4})
        full = {"no_change": 20, "ridge": 12, "boosted_trees": 8, "rates_lstm": 6, "news_lstm": 3}
        add(1, full)
        add(2, {n: e*2 for n, e in full.items()})
        add(3, full, eligible=False)
        add(4, full, config="old")
        add(5, full)  # Scored after cutoff.
        s.commit()
        evidence = scorecard(s, "USD", datetime(2026, 1, 10, tzinfo=utc), {"version": "current"},
            horizon=5, comparison_models=list(full))
        comparison = evidence["comparison"]
        assert evidence["distinct_outcomes"] == 3
        assert comparison["samples"] == 2
        assert comparison["candidates"]["ridge"]["mae_krw"] == 18
        assert comparison["history"][0]["mae"]["ridge"] == 12
        assert comparison["history"][1]["mae"]["ridge"] == 18
        assert evidence["candidates"]["ridge"]["samples"] == 3  # Original selection evidence unchanged.


def test_api_exposes_leaderboard_even_before_training(client):
    response = client.get("/api/v1/forecasts?horizon=10")
    assert response.status_code == 200
    board = response.json()["leaderboard"]
    assert board["horizon"] == 10 and board["matched_dates"] == 0
    assert any(row["model"] == "rates_lstm" for row in board["rows"])
