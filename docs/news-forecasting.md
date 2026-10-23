# Local news-aware forecasting

The dashboard includes a [model leaderboard](#model-leaderboard-and-longer-horizon-lstms), direct 1-, 3-, 5-, and 10-observation forecasts, a cost chart, an exchange-amount calculator, and evidence-gated purchase-timing signals. The one-day configuration remains `local-outlook-v5`; expanded longer-horizon competition uses `local-outlook-lstm-v6`.

The earlier `local-models-events-v4` version introduced no-change, ridge regression, boosted trees, and a rates LSTM; a news LSTM remains eligibility-gated. All inference is local.

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

The CPU LSTM uses 20 observations, 12 hidden units, 45 training epochs, and a fixed seed. Rate features describe returns, distance from MA5, and recent volatility. News features summarize the preceding seven days for KRW and the selected currency, across the six factors: reported counts, increase/decrease counts, expectation counts, reported actual percentage levels, explicit signed basis-point/percentage-point changes, previous and expected percentages, and numerical surprise (actual minus expected in percentage points). Expectations are not treated as realized numerical outcomes.

At least 160 daily observations are required. Three expanding chronological evaluation blocks contain 20 observations each, with a one-sample gap. The first two blocks select a candidate; the last block is held out from that selection. Scalers fit training data only. Selected candidates are subsequently refitted on the available labeled history.

The best rate-only candidate must improve validation price MAE over no-change by at least 2%. The news LSTM must improve over no-change and the best rates-only candidate by at least 2%. News eligibility additionally requires at least 30 training days containing news, 20 distinct first-seen dates, 15 validation days containing news, and 8 held-out days containing news. Passing these gates is not proof of future predictive advantage.

The panel shows validation and held-out MAE in KRW. Direction match is historical accuracy on a small test sample, not the probability of the next move. The displayed error band uses the held-out 80th-percentile absolute error; it is not a calibrated confidence interval. When eligible, masking news features reveals model sensitivity overall and by factor. These differences are diagnostics, not causal economic effects.

## Initial real-data result and limitations

On the initial local run, all eight currency forecasts were saved successfully. For USD, validation MAE was about KRW 6.64 for no-change versus KRW 7.18 for the rates LSTM, so no-change remained selected. The held-out block contained only 20 observations. The system does not claim the LSTM beat the baseline.

The available archive initially contained about 255 daily observations per pair and 110 articles, only 14 with full bodies. Those articles were first collected recently. They therefore provide no legitimate historical news features for the earlier evaluation windows. The news-enhanced path is implemented and exercised with synthetic point-in-time test data, but is deliberately ineligible on this initial real dataset. Continued collection builds usable history; backdating scraped articles would invalidate the evaluation.

## Components and verification

### Forward prediction scorecard

Forecast runs now record an explicit issue timestamp after training completes. Each candidate's prediction and the selected prediction are retained. New rate collection, analysis-only jobs, and forecast training settle pending predictions against the first stored daily observation after their source quote date. Outcomes store the actual won cost, signed error, and absolute error separately; issued forecasts are never rewritten. First-scored outcomes remain frozen if a source quote is corrected later.

Because exact quote publication timestamps are not archived, eligibility is conservative: issue time must precede midnight UTC at the start of the target quote date. Same-day and stale/backfilled predictions can be audited but do not enter the forward scorecard. The API serves read-only scores; collection/analysis/training performs settlement. Missing outcome dates are not invented or filled as weekend observations.

The Forecast panel's **Prediction vs. actual** section shows the latest five eligible outcomes and candidate MAEs against matched no-change errors. Selection uses at most the latest 90 distinct target dates, choosing the latest eligible issuance for each date. Repeated training on the same target date does not inflate the sample count. Results from different model configurations are kept separate.

At least 30 distinct scored dates are required to activate forward selection, and each candidate requires 30 paired outcomes. A candidate must beat no-change MAE by at least 2% and still pass the original chronological validation gate. News also requires its historical news gate and at least 30 matched outcomes against each rate-only competitor, with a 2% improvement over each. With enough baseline outcomes but insufficient candidate evidence, selection remains no-change. Before enough evidence accumulates, the existing historical selection remains in use. The selected candidate's historical error-band width follows that candidate; the displayed band remains uncalibrated.

This feedback changes future model selection. It does not feed tomorrow's error into today's inputs or claim automatic improvement. Parameters continue to be refitted on newly collected history by normal forecast jobs. Forward scores used for selection are development evidence, not an untouched final test. Configurations remain separate: the scorecard began with `local-lstm-news-v3`; the expanded competitors use `local-models-events-v4` and start their own forward history. Daily collection of 30 eligible quote dates is roughly six trading weeks; news eligibility can require longer. The backend must be running for scheduled collection; manual refresh can also settle results after new quotes arrive.

Migration `e531f0bc2c42` adds `forecast_outcomes`. The scorecard extension passed 77 backend tests, including weekend targets, absent outcomes, late issuance, immutable errors after rate revisions, configuration separation, timestamp cutoffs, deduplication, sample gates, and matched news/rates selection. Frontend lint/build passed. A real browser checked the live empty state and a browser-only synthetic 1,400 prediction / 1,410 actual / 10 error, with no page overflow at 1440px or 390px. Synthetic browser results were never written to the application database. See also [historical availability](historical-data.md).

- `app/services/news_facts.py`: local evidence extraction and revision history.
- `app/services/forecasting.py`: features, chronological evaluation, LSTM training, baseline selection, and diagnostics.
- `app/models/forecasts.py`: immutable evidence snapshots and stored forecast payloads.
- `GET /api/v1/forecasts?target_currency=USD`: latest forecast, freshness, and recent evidence.
- Forecast jobs: `QUEUED → EXTRACTING_HINTS → FORECASTING → COMPLETED`, with existing failure/retry recovery.
- Migrations: `c39fb91a7d20`, then `d420e9af1b31`.

Verification: 70 backend tests passed, including timestamp leakage, evidence revisions, numerical inputs, held-out isolation, and the synthetic news-model path. Frontend lint and production build passed. A real browser checked won units, model comparison, source links, navigation, and a 390px mobile layout. The existing read-only market audit passed, and Alembic reported no schema drift.

Implementation references: [PyTorch LSTM documentation](https://docs.pytorch.org/docs/stable/generated/torch.nn.LSTM.html) and [chronological split documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html). Splits are implemented locally. Scikit-learn is now an optional ML dependency for ridge regression and gradient boosting.


## Simple competitors and structured events

The v4 candidate roster is no-change, ridge regression, small gradient-boosted trees, rates-only LSTM, and (only when historical news coverage qualifies) the news LSTM. Ridge and trees flatten the same preceding 20 rate-feature observations that the rates LSTM sees. Ridge uses training-only standardization and fixed alpha 10. Trees use 60 estimators, depth 2, minimum leaf size 15, learning rate 0.05, and seed 42. Automatic random early stopping is disabled. No model is tuned using the final test block. All candidates use the same expanding folds, one-sample gap, validation targets, held-out targets, and prediction clipping. Parameters are fixed in `simple_forecasters.py` and included in each run's configuration.

The historical winner is selected on the first 40 validation targets, before inspecting the final 20. Forward selection compares rate-only competitors' recorded errors when at least 30 outcomes exist, while retaining their historical validation gate. The news candidate also needs matched forward comparisons against every rate-only competitor. Changing the candidate roster/configuration starts a separate scorecard cohort; old predictions and outcomes remain stored.

`economic_events.py` extracts supported sentence-level roles: indicator, currency association, reported/expected type, actual/previous/expected percentage, explicit change in basis points, and surprise relative to expectations. For example, "US inflation rose to 3% from 2%, expected at 2.8%" produces actual 3, previous 2, expected 2.8, and a +0.2 percentage-point surprise. A qualitative "above expectations" without an expected number retains a qualitative surprise and leaves numerical surprise unknown. Contradictory qualitative/numeric comparisons are marked conflicting and do not manufacture a numerical surprise.

Unknown values stay null. Forecasts do not become reported actuals. Negation, multiple currencies/indicators, multiple conflicting levels, and unsupported ranges suppress uncertain numerical assignments. A relative "fell by 2%" is not treated as a percentage-point change or a level. Basic Korean policy-rate statements are supported, but these rules are not general language understanding. Calendar periods, consensus provenance, full semantic parsing, implicit country context across sentences, and all phrasings/languages remain outside this extractor. Source claims are not independently verified.

Structured event fields are stored alongside immutable evidence and exposed in the Forecast panel. News vectors have nine channels per factor/currency group: four count channels plus actual percentage, explicit basis-point change, previous percentage, expected percentage, and numerical surprise. Expectations retain a separate count and do not enter reported-actual numerical channels. All availability, revision, and deduplication safeguards remain. The event migration is `f642a1cd3d53`; event extractor version is `local-events-v3`. Re-extraction creates new vintages rather than backdating improved parsing.

Verification: 97 backend tests passed, including curated extraction cases for actual/previous/expected figures, Korean text, negation, ambiguity, forecasts, ranges, and contradictory expectations. Tests also cover deterministic simple models, training-only scaling, held-out isolation for all competitors, structured numeric inputs, and forward selection of simple models. Frontend lint/build, real-browser model/event rendering, desktop/mobile overflow checks, and Alembic schema-drift checks passed. These are engineering checks, not a measured real-world extraction-accuracy benchmark.

The initial real v4 USD run kept no-change: validation MAE was approximately KRW 6.49 for baseline, 6.88 for ridge, 6.90 for trees, and 6.88 for rates LSTM. The held-out result did not override that selection. More models and more archived rates do not establish a predictive advantage.

Implementation references: [Ridge](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html), [GradientBoostingRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.GradientBoostingRegressor.html).

## Multi-day outlook and purchase timing

The default view compares buying the selected currency now with waiting five trading observations. Buttons select 1, 3, 5, or 10 observations after the latest stored quote. Prices are always KRW per one foreign unit, including JPY. The chart shows 15 recent observed quotes, each horizon's estimate, and each horizon's historical error range. Connecting lines interpolate visually between horizon estimates; they are not forecasts of every intervening day. Approximate dates skip weekends but do not implement a holiday calendar. All dates are explicitly anchored to the stored quote, not promised to be N calendar days from today.

Longer horizons use separate direct models of the cumulative log return from observation t to t+h. They are not repeated or linearly extrapolated one-day predictions. No-change, ridge, boosted trees, and a separately fitted rates LSTM now compete at every horizon. The news candidate remains available only for the one-observation horizon. Each horizon has its own validation scores, held-out scores, error bands, candidate predictions, selection, configuration, and forward scorecard.

Training examples end before their evaluation origin, using a horizon-sized training purge. Twenty-origin evaluation blocks are separated by h−1 origins so that validation labels cannot extend beyond the next block's first origin. The first 40 validation targets select the model; the final 20 are untouched by that selection. Forward selection remains subject to the original validation gates and 30 paired scored dates. Multi-day target windows can overlap, so distinct quote dates do not imply statistically independent errors. Bands remain empirical held-out errors, not calibrated confidence intervals.

`forecast_outcomes` now has a horizon field and a unique (run, horizon) constraint, added by migration `a753b2de4e64`. Settlement waits for the actual h-th observation after the source date, rather than assuming a calendar target date. Outcomes are immutable and mature independently. A long-horizon prediction issued after any part of its future path was already observed is excluded: issue must precede the first future quote's UTC day, not just the final target day. Existing one-step outcomes retain horizon 1. Model/configuration/horizon scorecards remain separate.

The purchase-timing banner is a transparent heuristic, not an extra trained model:

- **Model leans toward buying sooner** only when the horizon's forward gate is active, a non-baseline model is selected, inputs are fresh, and the entire historical error range is above the current reference cost.
- **Model leans toward waiting** requires the same evidence and a range entirely below the current cost.
- **No clear reason to buy now or wait** is shown for no-change, insufficient forward history, or a range crossing today's cost.
- **Refresh before deciding** suppresses timing signals for stale inputs, a source quote over four calendar days old, or an estimated target date already in the past.

The amount calculator estimates total KRW as foreign units × reference cost × (1 + markup/100). The user supplies the amount and markup; default markup 0 means fees are excluded. The same markup is assumed now and later, so it does not manufacture a timing advantage. Fixed fees, changing bank spreads, and the actual bank offer are not modeled. The user must choose a horizon compatible with when the currency is needed. No automatic purchase is made.

The UI collapses model/data details, forward accuracy history, and extracted news beneath the main decision, chart, and calculator. News remains context rather than an independent buy/sell instruction. Reference quote publication is on working days except TARGET closing days, so displayed weekday estimates can shift: [ECB reference-rate methodology](https://data.ecb.europa.eu/methodology/exchange-rates).

Verification: 109 backend tests pass, including direct horizon labels, training purges, validation/test separation, independent outcome maturity, rejection of late partial-path predictions, weekend dates, supported API horizons, and suppression of unsupported timing calls. Frontend lint/build and schema-drift checks pass. Real job 200 completed all eight currencies and four horizons. Browser checks covered the plotted chart, default five-day view, one/ten-day switching and scorecards, amount/markup arithmetic, invalid inputs, JPY units, and desktop/mobile page widths. The development server's stale generated stylesheet cache was moved aside and Next.js restarted; the chart now has its intended height and styling.

## Model leaderboard and longer-horizon LSTMs

The visible leaderboard under Forecast is specific to the selected currency and horizon. It shows the saved forecast choice, historical validation leaders, forward leaders, each model's MAE in KRW per foreign unit, improvement versus no-change, matched outcome counts, and evidence status. Tabs rank by validation or forward errors. The final held-out block is available in a separate diagnostic section and never determines leaderboard rank or model selection. Ties share ranks. A percentage improvement is undefined when baseline error is zero and is displayed as unknown, not an infinite percentage.

Forward ranking uses the same target quote dates across every candidate trained in the current forecast/configuration. A model missing on a date excludes that date from this comparison. This avoids ranking different samples as if they were equivalent. Late issues, future-scored outcomes, other currencies, other horizons, and other configurations are excluded. The scorecard's existing per-candidate matched-baseline evidence remains available to the established selection pipeline; the additional common-cohort comparison is read-only.

The performance chart tracks cumulative mean absolute forward error within the most recent 90-date scorecard window. It appears after two common scored dates; missing outcomes are never converted into zeros. A forward leader with fewer than 30 paired dates is explicitly provisional. A high rank alone does not replace the saved forecast. Retraining still applies the 2% validation and forward gates, minimum outcome counts, and additional news comparisons. Forward scores used to guide future selection are development evidence, not an untouched final test.

Rates LSTMs now train directly and separately at 1, 3, 5, and 10 observations. They use the same 20-observation rate-feature sequences, purged chronological folds, 45 epochs, and fixed parameters as the one-day LSTM. Each horizon predicts its own cumulative return and gets its own held-out error band and issued candidate forecast. Longer horizons use configuration `local-outlook-lstm-v6`; historical longer-horizon runs without an LSTM are retained but excluded from this new comparison. One-day training is unchanged and retains its exact `local-outlook-v5` configuration so its forward evidence is preserved. The legacy long-horizon registry field in that one-day configuration is kept for exact cohort compatibility and is overridden in longer-horizon payloads.

Current implementation paths after the package reorganization:

- `project/backend/app/services/forecasting/engine.py`: LSTM, horizon training, validation, and candidate forecasts.
- `project/backend/app/services/forecasting/scorecard.py`: actual outcomes, matched comparisons, and cumulative error history.
- `project/backend/app/services/forecasting/leaderboard.py`: read-only ranks and comparison statuses.
- `project/frontend/components/forecasts/forecast-leaderboard.tsx`: ranking table and performance chart.

The extension passed 114 backend tests and frontend lint/build. Tests cover all longer-horizon LSTM rosters and final-test isolation, unchanged one-day configuration, matched-date aggregation, missing candidates, temporal/configuration filters, ties, zero baseline error, and API serialization. Browser checks covered real 5/10-day LSTM rows, validation/forward ranking controls, one-day history preservation, and desktop/mobile widths. Browser-only synthetic outcomes exercised the populated forward-history chart and confirmed that rankings do not rewrite the current forecast choice; these outcomes were never stored in the database. No schema migration or paid service is required.

Real forecast job 211 completed successfully on October 21, 2026. API checks confirmed trained LSTM validation scores, held-out scores, and candidate predictions across all eight currencies and all four horizons (32 combinations). Longer horizons use the new configuration; one-day configuration and its existing eligible forward outcome were preserved. Training a candidate does not guarantee that it beats no-change or becomes the selected model.
