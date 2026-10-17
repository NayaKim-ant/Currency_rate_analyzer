# Local implementation verification

Verified on 2026-10-16. The local first-version implementation meets the functional completion criteria in the implementation plan.

## KRW home-currency update

The default collection/API base is KRW and the default target is USD. The dashboard requests `quote_direction=base_per_target`: the main rate, chart, and moving averages show the won cost of one foreign unit. Each daily quote is inverted before computing its averages and trend state. Lower chart values mean fewer won are needed to buy that currency. News, events, and alerts use the full currency pair to prevent results from the prior USD base appearing in the KRW view.

Direct provider KRW quotes lose precision for small values such as USD per won. The collector derives KRW quotes from precise USD-based inputs using Decimal division. The existing historical data was populated/recomputed for KRW, and existing articles were scored for its eight foreign-currency pairs. Historical USD data and rules retain their original meaning.

After the won-cost display correction: 42 backend tests passed; 2,040 KRW cross rates, 12,240 averages across 4,080 snapshots, 1,760 relevance records, and 48 pair/window combinations passed the database audit. The live dashboard rendered KRW-to-USD/EUR/JPY data with explicit won-per-foreign-unit price labels, including the chart and moving averages. Alembic detected no schema changes. Earlier comparison counts below describe the pre-KRW baseline.

## Current runtime

Collection and analysis now use a persistent PostgreSQL state machine with a durable queue, transition/attempt history, bounded retries, and crash recovery. Next.js displays and controls it under **Background logs**. The backend suite now has 60 passing tests, and a killed worker was recovered on the live database. Browser verification covered job submission, transition history, and manual retry. See [job state-machine details](job-state-machine.md).

The alert panel now supports won-cost targets at or below/above a user price, with create/pause/resume/delete and manual checks. Immediate evaluation, equality boundaries, one-quote inputs, missing data, currency validation, repeated-check deduplication, and notification history retention are covered by 51 passing backend tests. A headless Edge browser verified the form-to-database flow, immediate notification, pause/resume, delete/history retention, and phone-width layout. Temporary browser-test data was cleaned up. Alerts use daily reference quotes and appear in the dashboard, which polls every 30 seconds.

Next.js reads the FastAPI `/api/v1` endpoints. FastAPI queries PostgreSQL; the new runtime does not use the legacy Node IPC or JSON result files. SQLAlchemy models and Alembic manage the application schema. PostgreSQL stores rates, articles, relevance, keywords, trend snapshots, timeline events, alert rules, and alert occurrences.

The local API runs one APScheduler instance. Startup and daily schedules enqueue durable jobs; a worker collects inputs, analyzes stored data, and evaluates alerts through persisted stages. Independent Python worker commands use the same job queue, and execution can be moved into a separate worker process. PostgreSQL locks serialize competing pipeline workers and market read-modify-write operations. Database-backed job submission is now implemented.

## Legacy comparison

Used the archived `project/legacy/market_analysis_input.json` sample, covering 2026-08-21 through 2026-10-02. The audit executes the original Node `buildInsight` function without launching IPC or modifying legacy artifacts.

| Check | Result |
|---|---|
| Archived rate values versus PostgreSQL | All 248 observations match |
| Legacy latest MA5 and daily percentage change | Match for all eight currencies within legacy rounding precision |
| Independently recomputed MA5/MA20/MA60 | All 6,096 values/nulls match across 2,032 snapshots |
| Snapshot trend classifications | All 2,032 agree with the documented MA ordering rule |
| Persisted article scores and matching keywords | All 880 article/currency records agree with current scoring rules |
| Timeline identities | 119 events; no duplicates |
| Rates API windows | All eight currencies checked at 30, 90, and 365 days; same-date indicators agree |

Legacy trend labels intentionally differ: legacy compares the latest price with MA5 using a 0.15% gap, while the new system compares MA5, MA20, and MA60 and records signals through time. Legacy article selection uses substring matching and a two-keyword filter; the new system scores whole words/phrases per currency and distinguishes policy keywords. Neither collection counts nor article scores are expected to be identical between those methodologies. Historical news retrieval is also subject to RSS provider coverage.

## Issues corrected during verification

- Moving averages now include 59 earlier observations before the requested display window. Selecting a 30-day chart preserves MA60 when the database has enough earlier history.
- Article date filtering uses publication time, falling back to collection time only when publication time is unavailable. Historical backfill no longer appears as recent news merely because it was collected recently.
- Policy alerts require relevance to the rule's currency pair and produce one alert per rule/type/date even when multiple articles match.
- Rapid-rise/fall lookbacks use calendar dates and the last available quote on or before the baseline date, so non-trading days do not lengthen the configured period by an observation count.
- Reanalysis removes generated timeline signals invalidated by corrected source data. Alert occurrences remain historical records.
- PostgreSQL transaction locks protect concurrent analysis and related writes. Two simultaneous analysis runs completed without creating duplicate events.

## Execution checks

- Backend: 36 tests passed, including regression cases for the corrections above.
- Frontend: lint and production build passed in the preceding implementation verification; no frontend source changed during this audit.
- Live HTTP: the production dashboard rendered API-connected, database-backed content for KRW/30 days, EUR/90 days, and JPY/365 days. This verifies server rendering and API integration; browser interactions were not automated.
- Persistence: a clean PostgreSQL restart retained 2,032 rates, 110 articles, 2,032 snapshots, and 119 events during the preceding verification.
- Repeatability: repeated and concurrent analysis created zero additional events.

Run the read-only database audit from `project/backend`:

```powershell
.\.venv\Scripts\python.exe scripts/verify_market.py
```

It requires the existing local database, archived legacy sample, and Node on PATH. It verifies stored data without contacting news/rate providers or starting collection. Run backend regressions with `.\.venv\Scripts\python.exe -m pytest -q`.

The implementation is complete for local use. External email/messenger delivery, guaranteed historical news coverage, hosted deployment, and a distributed job queue are outside this version's scope.

## Local forecasting extension verification

70 backend tests passed, including evidence availability/revisions, future-data exclusion, numeric news features, held-out isolation, and synthetic news-LSTM training. Frontend lint/build and real-browser desktop/mobile forecast checks passed. The existing market audit passed and Alembic reported no schema drift. A real forecast job saved all eight currencies. The initial USD rates LSTM failed the validation baseline gate; the news candidate correctly remained ineligible because recent first-seen news cannot populate historical evaluation windows. See [forecasting report](news-forecasting.md).
