"""Forward errors are selection evidence, never inputs from an unknown future."""
import json
import math
from datetime import datetime, time, timezone
from statistics import mean
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.locks import lock_market_writes
from app.models.forecasts import ForecastOutcome, ForecastRun
from app.models.rates import ExchangeRate
from app.services.news.facts import as_utc

MIN_OUTCOMES = 30
WINDOW = 90


def configuration_key(configuration):
    return json.dumps(configuration, sort_keys=True)


def forecast_at_horizon(payload, horizon=1):
    if payload.get("horizon_forecasts"):
        return payload["horizon_forecasts"].get(str(horizon))
    return payload if horizon == 1 else None


def settle_forecasts(session: Session, now=None) -> int:
    now = as_utc(now or datetime.now(timezone.utc))
    lock_market_writes(session)
    existing = set(session.execute(select(ForecastOutcome.forecast_run_id, ForecastOutcome.horizon)).all())
    count = 0
    for run in session.scalars(select(ForecastRun).order_by(ForecastRun.id)):
        if run.payload.get("status") != "experimental" or as_utc(run.created_at) > now:
            continue
        horizons = [int(h) for h in run.payload.get("horizon_forecasts", {"1": run.payload})]
        pending = [h for h in horizons if (run.id, h) not in existing]
        if not pending:
            continue
        targets = list(session.scalars(select(ExchangeRate).where(
            ExchangeRate.base_currency == "KRW", ExchangeRate.target_currency == run.target_currency,
            ExchangeRate.rate_date > run.as_of_date, ExchangeRate.rate_date <= now.date(),
        ).order_by(ExchangeRate.rate_date).limit(max(pending))))
        for horizon in pending:
            payload = forecast_at_horizon(run.payload, horizon)
            if len(targets) < horizon or not payload or payload.get("status") != "experimental":
                continue
            target = targets[horizon-1]
            if as_utc(target.created_at) > now:
                continue
            actual = 1 / float(target.rate)
            eligible = as_utc(run.created_at) < datetime.combine(targets[0].rate_date, time.min, timezone.utc)
            errors = {}
            for name, predicted in payload.get("candidate_forecasts", {}).items():
                if not isinstance(predicted, (int, float)) or not math.isfinite(predicted) or predicted <= 0:
                    continue
                errors[name] = {"prediction": predicted, "absolute_error": abs(predicted-actual),
                                "signed_error": predicted-actual}
            if "no_change" not in errors:
                continue
            session.add(ForecastOutcome(forecast_run_id=run.id, horizon=horizon, target_date=target.rate_date,
                actual_cost=actual, eligible=eligible,
                reason="issued_before_first_target_day" if eligible else "issued_on_or_after_first_target_day",
                candidate_errors=errors, scored_at=now))
            count += 1
    session.commit()
    return count


def scorecard(session: Session, currency: str, cutoff=None, configuration=None, horizon=1):
    cutoff = as_utc(cutoff or datetime.now(timezone.utc))
    rows = session.execute(select(ForecastRun, ForecastOutcome).join(
        ForecastOutcome, ForecastOutcome.forecast_run_id == ForecastRun.id).where(
        ForecastRun.target_currency == currency, ForecastOutcome.eligible.is_(True), ForecastOutcome.horizon == horizon,
        ForecastOutcome.scored_at <= cutoff,
    ).order_by(ForecastOutcome.target_date.desc(), ForecastRun.created_at.desc(), ForecastRun.id.desc())).all()
    by_date = {}
    for run, outcome in rows:
        payload = forecast_at_horizon(run.payload, horizon)
        if not payload or (configuration is not None and configuration_key(payload.get("configuration", {})) != configuration_key(configuration)):
            continue
        view = SimpleNamespace(id=run.id, created_at=run.created_at, payload=payload)
        by_date.setdefault(outcome.target_date, (view, outcome))
    chosen = list(by_date.values())[:WINDOW]
    candidates = {}
    names = {name for _, outcome in chosen for name in outcome.candidate_errors}
    for name in sorted(names):
        paired = [o for _, o in chosen if name in o.candidate_errors and "no_change" in o.candidate_errors]
        candidates[name] = {"samples": len(paired),
            "mae_krw": mean(o.candidate_errors[name]["absolute_error"] for o in paired),
            "baseline_mae_krw": mean(o.candidate_errors["no_change"]["absolute_error"] for o in paired)}
    recent = [{"forecast_run_id": r.id, "issued_at": r.created_at, "target_date": o.target_date,
               "actual_cost": o.actual_cost, "model": r.payload["model"],
               "prediction": o.candidate_errors.get(r.payload["model"], {}).get("prediction"),
               "absolute_error": o.candidate_errors.get(r.payload["model"], {}).get("absolute_error")}
              for r, o in chosen[:5]]
    paired = [o for _, o in chosen if {"news_lstm", "rates_lstm"} <= o.candidate_errors.keys()]
    comparison = {"samples": len(paired),
                  "news_mae": mean(o.candidate_errors["news_lstm"]["absolute_error"] for o in paired),
                  "rates_mae": mean(o.candidate_errors["rates_lstm"]["absolute_error"] for o in paired)} if paired else None
    news_comparisons = {}
    for name in names - {"news_lstm", "no_change"}:
        paired = [o for _, o in chosen if {"news_lstm", name} <= o.candidate_errors.keys()]
        if paired:
            news_comparisons[name] = {"samples": len(paired),
                "news_mae": mean(o.candidate_errors["news_lstm"]["absolute_error"] for o in paired),
                "rates_mae": mean(o.candidate_errors[name]["absolute_error"] for o in paired)}
    return {"distinct_outcomes": len(chosen), "minimum_outcomes": MIN_OUTCOMES, "news_vs_rates": comparison,
            "horizon": horizon, "window": WINDOW, "candidates": candidates, "recent": recent, "news_comparisons": news_comparisons,
            "rule": "Latest eligible issuance per quote date; issue must precede target UTC day; outcomes frozen on first scoring."}


def apply_forward_selection(payload, evidence):
    """Past forward scores can gate future predictions; never rewrite past runs."""
    original = payload["model"]
    scores = evidence["candidates"]
    baseline = scores.get("no_change", {})
    selected = original
    if baseline.get("samples", 0) >= MIN_OUTCOMES:
        selected = "no_change"
        allowed = []
        for name, score in scores.items():
            if name == "no_change" or name not in payload["candidate_forecasts"] or score["samples"] < MIN_OUTCOMES:
                continue
            validation = payload["validation"]
            if validation[name]["mae_krw"] >= validation["no_change"]["mae_krw"] * .98:
                continue
            rate_names = set(payload["candidate_forecasts"]) - {"no_change", "news_lstm"}
            if name == "news_lstm" and (not payload["news"]["eligible"] or
                    validation[name]["mae_krw"] >= min(validation[n]["mae_krw"] for n in rate_names) * .98):
                continue
            if score["mae_krw"] < score["baseline_mae_krw"] * .98:
                allowed.append(name)
        rates_allowed = [name for name in allowed if name != "news_lstm"]
        if rates_allowed:
            selected = min(rates_allowed, key=lambda name: scores[name]["mae_krw"])
        if "news_lstm" in allowed:
            comparisons = evidence.get("news_comparisons", {})
            if not comparisons and evidence.get("news_vs_rates"):
                comparisons = {"rates_lstm": evidence["news_vs_rates"]}
            competitors = set(payload["candidate_forecasts"]) - {"news_lstm", "no_change"}
            if all(n in comparisons and comparisons[n]["samples"] >= MIN_OUTCOMES and
                   comparisons[n]["news_mae"] < comparisons[n]["rates_mae"] * .98 for n in competitors):
                selected = "news_lstm"
    point = payload["candidate_forecasts"][selected]
    width = payload["candidate_error_widths"][selected]
    payload.update(model=selected, forecast_cost=point, change_percent=(point/payload["current_cost"]-1)*100)
    payload["error_band"].update(lower=max(0, point-width), upper=point+width)
    payload["forward_selection"] = {"historical_choice": original, "choice": selected,
        "candidate_scores": scores,
        "distinct_outcomes": evidence["distinct_outcomes"], "minimum_outcomes": MIN_OUTCOMES,
        "active": baseline.get("samples", 0) >= MIN_OUTCOMES,
        "note": "Previous forward errors gate future model selection; they are not a confidence guarantee."}
