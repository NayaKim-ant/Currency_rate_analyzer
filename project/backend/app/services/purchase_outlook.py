"""Transparent purchase-timing heuristics, separate from model estimates."""
from datetime import date, datetime, timedelta, timezone


def estimated_quote_date(origin: date, horizon: int) -> date:
    # Weekdays are a display estimate, not a promise about market holidays.
    day = origin
    for _ in range(horizon):
        day += timedelta(days=1)
        while day.weekday() >= 5:
            day += timedelta(days=1)
    return day


def timing_signal(payload, origin, horizon=1, now=None, stale=False):
    now = now or datetime.now(timezone.utc)
    result = {"signal": "no_edge", "title": "No clear reason to buy now or wait",
              "reason": "The estimated move is smaller than the model's historical error range.",
              "estimated_date": estimated_quote_date(origin, horizon).isoformat(),
              "date_is_estimate": True}
    if not payload or payload.get("status") != "experimental":
        return {**result, "reason": "Train the multi-day models to see this horizon."}
    if stale or (now.date()-origin).days > 4 or estimated_quote_date(origin, horizon) < now.date():
        return {**result, "signal": "outdated", "title": "Refresh before deciding",
                "reason": "The source quote or forecast inputs are out of date."}
    if payload["model"] == "no_change":
        return {**result, "reason": "No model beat the no-change baseline strongly enough. A flat estimate is not a prediction that markets will stay flat."}
    if not payload.get("forward_selection", {}).get("active"):
        return {**result, "reason": "This horizon still needs at least 30 scored quote dates before its timing signal can be supported by forward results."}
    current = payload["current_cost"]
    lower, upper = payload["error_band"]["lower"], payload["error_band"]["upper"]
    if lower > current:
        return {**result, "signal": "buy_sooner", "title": "Model leans toward buying sooner",
                "reason": "The estimated future won cost is higher, even after allowing for historical model errors. Compare the bank's actual offer before acting."}
    if upper < current:
        return {**result, "signal": "wait", "title": "Model leans toward waiting",
                "reason": "The estimated future won cost is lower, even after allowing for historical model errors. Waiting still carries exchange-rate risk."}
    return result
