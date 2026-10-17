# Local news-aware forecasting

The dashboard's **Forecast** section estimates the next observed daily reference quote, expressed as KRW needed to buy one foreign unit. This is an experimental feature. It compares a small local LSTM against a no-change baseline and exposes the evidence and evaluation results. It does not predict bank fees or intraday exchange prices.

## Local setup and use

No LLM provider, API key, or paid inference service is used. Existing collectors still need internet access for public rates and news. Fact extraction and model training run locally on the CPU.

From `project/backend`, with the virtual environment activated:

```powershell
pip install -r requirements.txt
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-ml.txt
python -m alembic upgrade head
```

The ML dependencies and migrations are already installed/applied in this workspace. Start the backend and frontend normally, open `http://localhost:3000`, select a currency, and use **Forecast → Train local models**. This queues one job covering all eight supported foreign currencies. Progress and retries appear in Background logs. A CLI alternative is:

```powershell
python -m app.workers.run_jobs --job forecast --once
```

After the first saved forecast, completed rate and recent-news collections enqueue forecast refreshes automatically. A running worker is required. The API can serve without the optional ML dependencies; training reports an error if they are missing.

## What the extractor records

Local English/Korean rules identify interest rates, inflation, growth, employment, trade, and risk. Records retain exact source excerpts, source links, publication and first-availability times, currency associations, direction, and mentioned percentages or basis points. Expectations are separated from reported claims. Source claims are not independently verified.

Negation and multiple factors suppress ambiguous direction. Numeric figures in a sentence covering several factors remain visible as evidence but are excluded from numeric model inputs because their assignment is uncertain. Rules can miss paraphrases, misidentify entities, and cannot reliably interpret every economic relationship. There is no economic-calendar consensus/surprise dataset or general-purpose language understanding.

Evidence revisions preserve the old source snapshot and mark when it was superseded. A newly collected old article becomes available now, rather than on its old publication date. Historical features require both publication and availability before the decision cutoff, and exclude evidence superseded by that cutoff. Duplicate excerpts do not count as independent news signals.

## Model and evaluation

The CPU LSTM uses 20 observations, 12 hidden units, 45 training epochs, and a fixed seed. Rate features describe returns, distance from MA5, and recent volatility. News features summarize the preceding seven days for KRW and the selected currency, across the six factors: reported counts, increase/decrease counts, expectation counts, assigned percentage levels, and explicit signed basis-point/percentage-point changes. Expectations are not treated as realized numerical outcomes.

At least 160 daily observations are required. Three expanding chronological evaluation blocks contain 20 observations each, with a one-sample gap. The first two blocks select a candidate; the last block is held out from that selection. Scalers fit training data only. Selected candidates are subsequently refitted on the available labeled history.

The rates-only LSTM must improve validation price MAE over no-change by at least 2%. The news LSTM must improve over both alternatives by at least 2%. News eligibility additionally requires at least 30 training days containing news, 20 distinct first-seen dates, 15 validation days containing news, and 8 held-out days containing news. Passing these gates is not proof of future predictive advantage.

The panel shows validation and held-out MAE in KRW. Direction match is historical accuracy on a small test sample, not the probability of the next move. The displayed error band uses the held-out 80th-percentile absolute error; it is not a calibrated confidence interval. When eligible, masking news features reveals model sensitivity overall and by factor. These differences are diagnostics, not causal economic effects.

## Initial real-data result and limitations

On the initial local run, all eight currency forecasts were saved successfully. For USD, validation MAE was about KRW 6.64 for no-change versus KRW 7.18 for the rates LSTM, so no-change remained selected. The held-out block contained only 20 observations. The system does not claim the LSTM beat the baseline.

The available archive initially contained about 255 daily observations per pair and 110 articles, only 14 with full bodies. Those articles were first collected recently. They therefore provide no legitimate historical news features for the earlier evaluation windows. The news-enhanced path is implemented and exercised with synthetic point-in-time test data, but is deliberately ineligible on this initial real dataset. Continued collection builds usable history; backdating scraped articles would invalidate the evaluation.

## Components and verification

- `app/services/news_facts.py`: local evidence extraction and revision history.
- `app/services/forecasting.py`: features, chronological evaluation, LSTM training, baseline selection, and diagnostics.
- `app/models/forecasts.py`: immutable evidence snapshots and stored forecast payloads.
- `GET /api/v1/forecasts?target_currency=USD`: latest forecast, freshness, and recent evidence.
- Forecast jobs: `QUEUED → EXTRACTING_HINTS → FORECASTING → COMPLETED`, with existing failure/retry recovery.
- Migrations: `c39fb91a7d20`, then `d420e9af1b31`.

Verification: 70 backend tests passed, including timestamp leakage, evidence revisions, numerical inputs, held-out isolation, and the synthetic news-model path. Frontend lint and production build passed. A real browser checked won units, model comparison, source links, navigation, and a 390px mobile layout. The existing read-only market audit passed, and Alembic reported no schema drift.

Implementation references: [PyTorch LSTM documentation](https://docs.pytorch.org/docs/stable/generated/torch.nn.LSTM.html) and [chronological split documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html). Splits are implemented locally; scikit-learn is not a dependency.
