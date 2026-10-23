"""Read-only rankings: validation and genuine forward outcomes stay separate."""
import math

MODEL_ORDER = ("no_change", "ridge", "boosted_trees", "rates_lstm", "news_lstm")


def gain(error, baseline):
    if error is None or baseline is None or baseline <= 0:
        return None
    return (baseline-error)/baseline*100


def ranks(values):
    ordered = sorted(values, key=lambda name: (values[name], MODEL_ORDER.index(name) if name in MODEL_ORDER else 99, name))
    result = {}
    last, rank = None, 0
    for index, name in enumerate(ordered, start=1):
        if last is None or not math.isclose(values[name], last, rel_tol=1e-12, abs_tol=1e-12):
            rank = index
        result[name] = rank
        last = values[name]
    return result


def build_leaderboard(forecast, evidence, horizon=1):
    forecast = forecast or {}
    validation = forecast.get("validation", {})
    comparison = evidence.get("comparison", {})
    forward = comparison.get("candidates", {})
    minimum = evidence.get("minimum_outcomes", 30)
    samples = comparison.get("samples", 0)
    baseline = validation.get("no_change", {}).get("mae_krw")
    validation_ranks = ranks({name: score["mae_krw"] for name, score in validation.items()})
    forward_ranks = ranks({name: score["mae_krw"] for name, score in forward.items()})
    predictions = forecast.get("candidate_forecasts", {})
    selected = forecast.get("model")
    rows = []
    for name in dict.fromkeys([*MODEL_ORDER, *validation]):
        val = validation.get(name, {})
        live = forward.get(name, {})
        historical_gain = gain(val.get("mae_krw"), baseline)
        forward_gain = gain(live.get("mae_krw"), live.get("baseline_mae_krw"))
        if name not in validation:
            status = "not_supported" if name == "news_lstm" and horizon > 1 else "news_history" if name == "news_lstm" else "needs_training"
        elif name == "no_change":
            status = "baseline"
        elif historical_gain is None or historical_gain <= 2:
            status = "validation_gate"
        elif samples < minimum:
            status = "collecting"
        elif forward_gain is None or forward_gain <= 2:
            status = "forward_gate"
        else:
            status = "eligible"
        if name == "news_lstm" and status == "eligible":
            rate_names = set(validation) - {"news_lstm", "no_change"}
            if (not forecast.get("news", {}).get("eligible") or any(
                val["mae_krw"] >= validation[n]["mae_krw"]*.98 or
                n not in forward or live["mae_krw"] >= forward[n]["mae_krw"]*.98 for n in rate_names)):
                status = "news_comparison_gate"
        rows.append({"model": name, "selected": selected == name, "status": status,
            "validation_rank": validation_ranks.get(name), "forward_rank": forward_ranks.get(name),
            "validation_mae": val.get("mae_krw"), "validation_samples": val.get("samples", 0),
            "validation_gain_percent": historical_gain,
            "held_out_mae": forecast.get("held_out_test", {}).get(name, {}).get("mae_krw"),
            "forward_mae": live.get("mae_krw"), "forward_samples": live.get("samples", 0),
            "forward_gain_percent": forward_gain, "forecast_cost": predictions.get(name)})
    return {"horizon": horizon, "selected_model": selected,
        "validation_leaders": [n for n, rank in validation_ranks.items() if rank == 1],
        "forward_leaders": [n for n, rank in forward_ranks.items() if rank == 1],
        "forward_ready": samples >= minimum, "matched_dates": samples, "minimum_outcomes": minimum,
        "window": evidence.get("window", 90), "rows": rows, "history": comparison.get("history", []),
        "configuration_version": forecast.get("configuration", {}).get("version"),
        "note": "Forward ranks use the same target dates for all trained candidates in this currency, horizon and configuration. Rankings alone do not change the issued forecast."}
