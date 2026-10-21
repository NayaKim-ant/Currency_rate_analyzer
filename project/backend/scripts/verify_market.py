"""Read-only audit of the legacy sample and current persisted calculations.

Run from project/backend: python scripts/verify_market.py
The old Node calculation runs without its IPC/process startup code.
"""

import json
import subprocess
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.main import app
from app.models.news import Article, ArticleRelevance
from app.models.rates import ExchangeRate, MarketEvent, TrendSnapshot
from app.services.news.relevance import score_article


def main() -> None:
    legacy = Path(__file__).resolve().parents[2] / "legacy"
    archived = json.loads((legacy / "market_analysis_input.json").read_text(encoding="utf-8"))
    runner = """
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const definitions = source.slice(0, source.indexOf('if (!isMainThread)'));
const context = vm.createContext({require});
vm.runInContext(definitions, context);
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(context.buildInsight(input)));
"""
    result = subprocess.run(
        ["node", "-e", runner, str(legacy / "node_process.js")],
        input=json.dumps(archived), text=True, encoding="utf-8", capture_output=True, check=True, timeout=30,
    )
    legacy_output = json.loads(result.stdout)
    report = {}
    with SessionLocal() as session:
        rates = list(session.scalars(select(ExchangeRate).order_by(ExchangeRate.rate_date)))
        lookup = {(r.base_currency, r.target_currency, r.rate_date): r.rate for r in rates}
        compared = 0
        for entry in archived["rates"]:
            for currency, value in entry["rates"].items():
                key = (entry["base"], currency, date.fromisoformat(entry["date"]))
                assert key in lookup, f"Missing archived observation: {key}"
                assert abs(lookup[key] - Decimal(str(value))) <= Decimal("0.0000000001"), key
                compared += 1
        report["legacy_observations_matched"] = compared

        cross_checks = 0
        for row in rates:
            if row.base_currency != "KRW":
                continue
            denominator = lookup.get(("USD", "KRW", row.rate_date))
            numerator = Decimal("1") if row.target_currency == "USD" else lookup.get(("USD", row.target_currency, row.rate_date))
            if denominator is not None and numerator is not None:
                assert abs(row.rate - numerator / denominator) <= Decimal("0.0000000001"), (
                    "KRW cross-rate precision", row.target_currency, row.rate_date,
                )
                cross_checks += 1
        report["precise_krw_cross_rates_checked"] = cross_checks

        snapshots = list(session.scalars(select(TrendSnapshot)))
        snapshot_lookup = {(r.base_currency, r.target_currency, r.as_of_date): r for r in snapshots}
        for currency, insight in legacy_output["currencies"].items():
            snapshot = snapshot_lookup[("USD", currency, date.fromisoformat(insight["latest_date"]))]
            assert abs(snapshot.ma_5 - Decimal(str(insight["five_day_moving_average"]))) <= Decimal("0.000001")
            assert abs(snapshot.daily_change_percent - Decimal(str(insight["change_from_previous_day_percent"]))) <= Decimal("0.0005")
        report["legacy_latest_ma5_and_daily_change_matched"] = len(legacy_output["currencies"])

        grouped = defaultdict(list)
        for row in rates:
            grouped[(row.base_currency, row.target_currency)].append(row)
        average_checks = 0
        for (base, target), rows in grouped.items():
            for index, row in enumerate(rows):
                snapshot = snapshot_lookup[(base, target, row.rate_date)]
                expected = []
                for window in (5, 20, 60):
                    value = None if index + 1 < window else sum(
                        (r.rate for r in rows[index + 1 - window:index + 1]), Decimal(0),
                    ) / window
                    actual = getattr(snapshot, f"ma_{window}")
                    assert (actual is None) == (value is None), (base, target, row.rate_date, window)
                    if value is not None:
                        assert abs(actual - value) <= Decimal("0.0000000001"), (base, target, row.rate_date, window)
                    expected.append(value)
                    average_checks += 1
                state = "insufficient_data" if None in expected else (
                    "uptrend" if expected[0] > expected[1] > expected[2] else
                    "downtrend" if expected[0] < expected[1] < expected[2] else "neutral"
                )
                assert snapshot.trend_state == state
        report["independent_moving_average_checks"] = average_checks
        report["trend_snapshots_checked"] = len(snapshots)

        articles = {a.id: a for a in session.scalars(select(Article))}
        relevance_checks = 0
        for relevance in session.scalars(select(ArticleRelevance)):
            article = articles[relevance.article_id]
            expected = score_article(article.title, article.content or article.summary, relevance.target_currency)
            assert relevance.score == expected.score
            assert set(relevance.matched_keywords) == set(expected.matched_keywords)
            relevance_checks += 1
        report["persisted_article_scores_checked"] = relevance_checks

        identities = set()
        for event in session.scalars(select(MarketEvent)):
            key = (event.base_currency, event.target_currency, event.event_type, event.occurred_at, event.article_id)
            assert key not in identities, f"Duplicate timeline event: {key}"
            identities.add(key)
        report["unique_timeline_events_checked"] = len(identities)

    # No lifespan context: querying the live DB must not trigger collection.
    client = TestClient(app)
    endpoint_checks = 0
    for base, target in grouped:
        latest_by_window = []
        for days in (30, 90, 365):
            response = client.get(f"/api/v1/rates?base_currency={base}&target_currency={target}&days={days}")
            assert response.status_code == 200
            payload = response.json()
            for point in payload["points"]:
                snapshot = snapshot_lookup[(base, target, date.fromisoformat(point["rate_date"]))]
                for window in (5, 20, 60):
                    actual = point[f"ma_{window}"]
                    expected = getattr(snapshot, f"ma_{window}")
                    assert (actual is None) == (expected is None)
                    if actual is not None:
                        assert abs(Decimal(str(actual)) - expected) <= Decimal("0.0000000001")
            latest_by_window.append(payload["points"][-1] if payload["points"] else None)
            endpoint_checks += 1
        assert latest_by_window[0] == latest_by_window[1] == latest_by_window[2]
    report["currency_and_display_window_checks"] = endpoint_checks
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
