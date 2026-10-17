"""CPU LSTM experiments with point-in-time news and a no-change benchmark."""

import hashlib
import json
import re
from datetime import datetime, time, timedelta, timezone

import numpy as np
import torch
from sqlalchemy import select
from sqlalchemy.orm import Session
from torch import nn

from app.core.currencies import FOREIGN_CURRENCIES
from app.models.forecasts import ForecastRun, NewsFact
from app.models.market import ExchangeRate
from app.services.news_facts import FACTORS, as_utc

SEQUENCE = 20
MIN_OBSERVATIONS = 160
PRICE_FEATURES = 3
CONFIG = {"version": "local-lstm-news-v2", "sequence": SEQUENCE, "hidden_size": 12,
          "epochs": 45, "seed": 42, "horizon_observations": 1, "news_window_days": 7,
          "news_channels": ["reported_count", "increase_count", "decrease_count", "expectation_count",
                            "mentioned_percentage_mean", "explicit_change_basis_points"]}


def news_vector(facts: list[NewsFact], currency: str, cutoff: datetime) -> list[float]:
    """Only use immutable evidence actually available at the decision cutoff."""
    cutoff = as_utc(cutoff)
    start = cutoff - timedelta(days=7)
    vector = np.zeros((2, len(FACTORS), 6), dtype=np.float64)
    percentages = {}
    seen = set()
    for fact in facts:
        if as_utc(fact.available_at) > cutoff or fact.published_at is None:
            continue
        if fact.superseded_at is not None and as_utc(fact.superseded_at) <= cutoff:
            continue
        if not start <= as_utc(fact.published_at) <= cutoff or fact.claim_type == "commentary":
            continue
        identity = (fact.factor, fact.evidence.casefold(), tuple(sorted(fact.currencies)))
        if identity in seen:
            continue  # Syndicated excerpts do not count repeatedly across URLs.
        seen.add(identity)
        for group, affected in enumerate(("KRW", currency)):
            global_risk = fact.factor == "risk" and not fact.currencies
            if (affected not in fact.currencies and not global_risk) or fact.factor not in FACTORS:
                continue
            factor = list(FACTORS).index(fact.factor)
            if fact.claim_type == "forward_looking":
                vector[group, factor, 3] += 1
            else:
                vector[group, factor, 0] += 1
                if fact.direction == "increase":
                    vector[group, factor, 1] += 1
                elif fact.direction == "decrease":
                    vector[group, factor, 2] += 1
                for figure in fact.figures:
                    if not figure.get("assigned", False):
                        continue  # Multiple economic variables: magnitude attribution is unclear.
                    unit, value = figure["unit"].lower(), float(figure["value"])
                    if unit == "%" or (unit.startswith("percent") and "point" not in unit):
                        percentages.setdefault((group, factor), []).append(value)
                    if ("basis" in unit or unit.startswith("bp") or "percentage point" in unit) and re.search(
                        r"\bby\s+" + re.escape(figure["text"]), fact.evidence, re.I,
                    ):
                        signed = value if fact.direction == "increase" else -value if fact.direction == "decrease" else 0
                        vector[group, factor, 5] += signed * (100 if "percentage point" in unit else 1)
    vector[:, :, :4] = np.log1p(vector[:, :, :4])
    for (group, factor), values in percentages.items():
        vector[group, factor, 4] = np.clip(np.mean(values), -100, 100) / 10
    vector[:, :, 5] = np.clip(vector[:, :, 5] / 100, -5, 5)
    return vector.reshape(-1).tolist()


def build_dataset(rates, facts, currency, now):
    costs = np.array([1 / float(row.rate) for row in rates], dtype=np.float64)
    returns = np.zeros(len(costs))
    returns[1:] = np.log(costs[1:] / costs[:-1]) * 100
    rows = []
    for index, row in enumerate(rates):
        cutoff = min(as_utc(now), datetime.combine(row.rate_date, time.max, tzinfo=timezone.utc))
        gap = np.log(costs[index] / np.mean(costs[max(0, index-4):index+1])) * 100
        volatility = float(np.std(returns[max(1, index-19):index+1])) if index else 0
        rows.append([returns[index], gap, volatility, *news_vector(facts, currency, cutoff)])
    features = np.asarray(rows, dtype=np.float64)
    origins = list(range(SEQUENCE - 1, len(costs) - 1))
    x = np.array([features[i-SEQUENCE+1:i+1] for i in origins])
    y = np.array([returns[i+1] for i in origins])
    return costs, features, origins, x, y


class LocalLSTM(nn.Module):
    def __init__(self, width):
        super().__init__()
        self.memory = nn.LSTM(width, CONFIG["hidden_size"], batch_first=True)
        self.head = nn.Linear(CONFIG["hidden_size"], 1)

    def forward(self, values):
        outputs, _ = self.memory(values)
        return self.head(outputs[:, -1]).squeeze(-1)


def fit_model(x, y, epochs=None):
    torch.manual_seed(CONFIG["seed"])
    mean = x.mean(axis=(0, 1))
    scale = x.std(axis=(0, 1))
    scale[scale < 1e-8] = 1
    y_mean, y_scale = float(y.mean()), max(float(y.std()), 0.05)
    inputs = torch.tensor(np.clip((x - mean) / scale, -8, 8), dtype=torch.float32)
    targets = torch.tensor((y - y_mean) / y_scale, dtype=torch.float32)
    model = LocalLSTM(x.shape[-1])
    optimizer = torch.optim.Adam(model.parameters(), lr=0.005, weight_decay=0.01)
    model.train()
    for _ in range(epochs or CONFIG["epochs"]):
        optimizer.zero_grad()
        loss = nn.functional.mse_loss(model(inputs), targets)
        if not torch.isfinite(loss):
            raise ValueError("LSTM training produced a non-finite loss")
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1)
        optimizer.step()
    model.eval()
    return model, mean, scale, y_mean, y_scale


def predict_model(fitted, x):
    model, mean, scale, y_mean, y_scale = fitted
    with torch.no_grad():
        result = model(torch.tensor(np.clip((x-mean)/scale, -8, 8), dtype=torch.float32)).numpy()
    return np.clip(result * y_scale + y_mean, -5*y_scale, 5*y_scale).astype(np.float64)


def metrics(predicted_returns, actual_returns, current_costs):
    predicted = current_costs * np.exp(predicted_returns / 100)
    actual = current_costs * np.exp(actual_returns / 100)
    error = np.abs(predicted - actual)
    moving = (np.abs(actual_returns) > 1e-8) & (np.abs(predicted_returns) > 1e-8)
    accuracy = float(np.mean(np.sign(predicted_returns[moving]) == np.sign(actual_returns[moving]))) if moving.any() else None
    return {"mae_krw": float(error.mean()), "direction_accuracy": accuracy, "samples": len(error)}, error


def train_pair(rates, facts, currency, now, epochs=None):
    torch.set_num_threads(1)
    if len(rates) < MIN_OBSERVATIONS:
        return {"status": "insufficient_data", "observations": len(rates), "minimum_observations": MIN_OBSERVATIONS}
    costs, features, origins, x, y = build_dataset(rates, facts, currency, now)
    count = len(y)
    starts = [count-60, count-40, count-20]
    first_cutoff = datetime.combine(rates[origins[starts[0]]].rate_date, time.max, tzinfo=timezone.utc)
    available_days = {as_utc(f.available_at).date() for f in facts if as_utc(f.available_at) < first_cutoff
                      and f.published_at is not None and (({"KRW", currency} & set(f.currencies))
                                                         or (f.factor == "risk" and not f.currencies))}
    has_news = (features[:, PRICE_FEATURES:] != 0).any(axis=1)
    training_news_days = int(has_news[:origins[starts[0]]].sum())
    validation_news_days = int(has_news[origins[starts[0]]:origins[starts[2]]].sum())
    test_news_days = int(has_news[origins[starts[2]]:].sum())
    news_eligible = (training_news_days >= 30 and len(available_days) >= 20
                     and validation_news_days >= 15 and test_news_days >= 8)
    candidates = ["no_change", "rates_lstm"] + (["news_lstm"] if news_eligible else [])
    outputs = {name: [] for name in candidates}
    folds = []
    for start in starts:
        end = min(start+20, count)
        folds.append({"train_samples": start-1, "first_origin": rates[origins[start]].rate_date.isoformat(),
                      "last_origin": rates[origins[end-1]].rate_date.isoformat(), "evaluation_samples": end-start})
        outputs["no_change"].append(np.zeros(end-start))
        for name in candidates[1:]:
            width = PRICE_FEATURES if name == "rates_lstm" else x.shape[-1]
            # One-sample gap; scaling and fitting see only the expanding past.
            fitted = fit_model(x[:start-1, :, :width], y[:start-1], epochs)
            outputs[name].append(predict_model(fitted, x[start:end, :, :width]))
    val_y = y[starts[0]:starts[2]]
    val_costs = costs[np.array(origins[starts[0]:starts[2]])]
    scores = {}
    for name in candidates:
        scores[name], _ = metrics(np.concatenate(outputs[name][:2]), val_y, val_costs)
    selected = "no_change"
    if scores["rates_lstm"]["mae_krw"] < scores["no_change"]["mae_krw"] * 0.98:
        selected = "rates_lstm"
    if news_eligible and scores["news_lstm"]["mae_krw"] < min(
        scores["no_change"]["mae_krw"], scores["rates_lstm"]["mae_krw"],
    ) * 0.98:
        selected = "news_lstm"
    # Selection is frozen before the final, untouched block is scored.
    tests = {}
    residuals = None
    for name in candidates:
        tests[name], errors = metrics(outputs[name][2], y[starts[2]:], costs[np.array(origins[starts[2]:])])
        if name == selected:
            residuals = errors
    final_input = features[-SEQUENCE:].copy()
    final_input[-1, PRICE_FEATURES:] = news_vector(facts, currency, now)
    forecasts = {"no_change": float(costs[-1])}
    news_sensitivity = None
    factor_sensitivities = {}
    for name in candidates[1:]:
        width = PRICE_FEATURES if name == "rates_lstm" else x.shape[-1]
        fitted = fit_model(x[:, :, :width], y, epochs)
        prediction = float(predict_model(fitted, final_input[None, :, :width])[0])
        forecasts[name] = float(costs[-1] * np.exp(prediction / 100))
        if name == "news_lstm":
            masked = final_input.copy()
            masked[:, PRICE_FEATURES:] = 0
            masked_return = float(predict_model(fitted, masked[None])[0])
            news_sensitivity = forecasts[name] - float(costs[-1] * np.exp(masked_return / 100))
            for index, factor in enumerate(FACTORS):
                masked_factor = final_input.copy()
                for group in range(2):
                    offset = PRICE_FEATURES + (group*len(FACTORS)+index)*6
                    masked_factor[:, offset:offset+6] = 0
                ablated = float(predict_model(fitted, masked_factor[None])[0])
                factor_sensitivities[factor] = forecasts[name] - float(costs[-1]*np.exp(ablated/100))
    point = forecasts[selected]
    width = float(np.quantile(residuals, 0.8))
    dataset_hash = hashlib.sha256(json.dumps({"rates": [(r.rate_date.isoformat(), str(r.rate)) for r in rates],
        "facts": [(f.evidence_hash, as_utc(f.available_at).isoformat(), str(f.superseded_at)) for f in facts]}, sort_keys=True).encode()).hexdigest()
    return {"status": "experimental", "generated_at": now.isoformat(), "as_of_date": rates[-1].rate_date.isoformat(),
        "horizon": "next_available_daily_quote", "rate_currency": "KRW", "unit_currency": currency,
        "current_cost": float(costs[-1]), "forecast_cost": point, "change_percent": (point/costs[-1]-1)*100,
        "model": selected, "candidate_forecasts": forecasts,
        "error_band": {"lower": max(0, point-width), "upper": point+width,
                       "description": "80th percentile of absolute held-out errors; not a calibrated confidence interval"},
        "validation": scores, "held_out_test": tests, "folds": folds, "dataset_hash": dataset_hash,
        "observations": len(rates), "configuration": {**CONFIG, "epochs": epochs or CONFIG["epochs"]},
        "selection": "First two expanding-window blocks select a model only after a 2% MAE improvement; final block is untouched until selection.",
        "news": {"eligible": news_eligible, "training_news_days": training_news_days,
                 "first_seen_dates": len(available_days), "validation_news_days": validation_news_days,
                 "test_news_days": test_news_days, "sensitivity_krw": news_sensitivity,
                 "factor_sensitivities": factor_sensitivities,
                 "status": "validated_candidate" if news_eligible else "collecting_point_in_time_history",
                 "requirements": "30 training news days across 20 first-seen dates, 15 validation days, and 8 test days.",
                 "note": "First-seen/extraction times prevent backfilled news from leaking into earlier predictions. No fixed causal direction is assumed."}}


def train_forecasts(session: Session) -> int:
    now = datetime.now(timezone.utc)
    facts = list(session.scalars(select(NewsFact).order_by(NewsFact.id)))
    count = 0
    for currency in FOREIGN_CURRENCIES:
        rates = list(session.scalars(select(ExchangeRate).where(
            ExchangeRate.base_currency == "KRW", ExchangeRate.target_currency == currency,
            ExchangeRate.rate_date <= now.date(),
        ).order_by(ExchangeRate.rate_date)))
        if not rates:
            continue
        payload = train_pair(rates, facts, currency, now)
        session.add(ForecastRun(target_currency=currency, as_of_date=rates[-1].rate_date, payload=payload))
        count += 1
    session.commit()
    return count
