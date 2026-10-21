import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("sklearn")
pytest.importorskip("torch")

from app.services.forecasting.simple_models import fit_simple, predict_simple
from app.services.forecasting import engine as forecasting
from app.services.forecasting.scorecard import apply_forward_selection
from tests.test_forecast_scorecard import payload, evidence
from tests.test_forecasting import history, fact
from datetime import datetime, timedelta, timezone


@pytest.mark.parametrize("name", ["ridge", "boosted_trees"])
def test_simple_competitors_fit_only_training_rows_and_are_deterministic(name):
    random = np.random.default_rng(123)
    x = random.normal(size=(100, 20, 3))
    y = x[:, -1, 0] * .3
    model = fit_simple(name, x[:80], y[:80])
    predicted = predict_simple(model, x[80:])
    assert predicted.shape == (20,) and np.isfinite(predicted).all()
    repeated = predict_simple(fit_simple(name, x[:80], y[:80]), x[80:])
    np.testing.assert_allclose(predicted, repeated)
    y[80:] += 1000
    x[80:] += 1000
    np.testing.assert_allclose(predict_simple(fit_simple(name, x[:80], y[:80]), np.zeros((1, 20, 3))),
                               predict_simple(model, np.zeros((1, 20, 3))))
    if name == "ridge":
        np.testing.assert_allclose(model[0][0].mean_, x[:80].reshape(80, -1).mean(axis=0))


def test_all_candidates_share_time_splits_and_final_test_cannot_select_models():
    rates, now = history()
    original = forecasting.train_pair(rates, [], "USD", now, epochs=1)
    assert set(original["candidate_forecasts"]) == {"no_change", "ridge", "boosted_trees", "rates_lstm"}
    assert all(score["samples"] == 40 for score in original["validation"].values())
    rates[-1].rate *= 2
    changed = forecasting.train_pair(rates, [], "USD", now, epochs=1)
    assert original["validation"] == changed["validation"] and original["model"] == changed["model"]


def test_structured_event_numbers_are_separate_point_in_time_features():
    now = datetime(2026, 10, 17, tzinfo=timezone.utc)
    row = fact(now-timedelta(days=1), now-timedelta(hours=1), event={"attribution": "single_currency_factor",
        "actual": 3., "previous": 4., "expected": 2.8, "surprise_percentage_points": .2, "change_basis_points": None})
    v = np.array(forecasting.news_vector([row], "USD", now)).reshape(2, 6, forecasting.NEWS_CHANNELS)
    np.testing.assert_allclose(v[1, 1, [4, 6, 7, 8]], [.3, .4, .28, .02])
    assert not any(forecasting.news_vector([row], "USD", now-timedelta(days=2)))


def test_forward_selection_can_choose_simple_model_and_requires_news_to_beat_it():
    p = payload()
    for name in ["ridge", "boosted_trees"]:
        p["candidate_forecasts"][name] = 1401
        p["candidate_error_widths"][name] = 10
        p["validation"][name] = {"mae_krw": 9}
    e = evidence(30)
    e["candidates"]["ridge"] = {"samples": 30, "mae_krw": 5, "baseline_mae_krw": 10}
    e["candidates"]["boosted_trees"] = {"samples": 30, "mae_krw": 7, "baseline_mae_krw": 10}
    apply_forward_selection(p, e)
    assert p["model"] == "ridge" and p["forecast_cost"] == 1401
    p["candidate_forecasts"]["news_lstm"] = 1402
    p["candidate_error_widths"]["news_lstm"] = 8
    p["validation"]["news_lstm"] = {"mae_krw": 6}
    p["news"]["eligible"] = True
    e["candidates"]["news_lstm"] = {"samples": 30, "mae_krw": 4, "baseline_mae_krw": 10}
    e["news_comparisons"] = {name: {"samples": 30, "news_mae": 4, "rates_mae": 5} for name in ["rates_lstm", "ridge"]}
    apply_forward_selection(p, e)
    assert p["model"] == "ridge"  # Missing matched tree comparison.
    e["news_comparisons"]["boosted_trees"] = {"samples": 30, "news_mae": 4, "rates_mae": 5}
    apply_forward_selection(p, e)
    assert p["model"] == "news_lstm"
