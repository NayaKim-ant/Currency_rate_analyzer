# Persistent background job state machine

Collection and analysis now run through a PostgreSQL-backed state machine. FastAPI remains responsible for HTTP requests, and Next.js shows progress in **Background logs**. No Redis, Celery, or external message broker is required.

## States

| State | Meaning | Allowed next states |
|---|---|---|
| `QUEUED` | Waiting for its scheduled start and a worker | `COLLECTING`, `ANALYZING` for analysis-only work, or `EXTRACTING_HINTS` for forecasts |
| `COLLECTING` | Fetching and upserting rates or news | `ANALYZING`, `FAILED` |
| `ANALYZING` | Updating trend snapshots and market events | `EVALUATING_ALERTS`, `FAILED` |
| `EVALUATING_ALERTS` | Checking enabled alert rules against stored data | `COMPLETED`, `FAILED` |
| `EXTRACTING_HINTS` | Extracting local news evidence | `FORECASTING`, `FAILED` |
| `FORECASTING` | Training/evaluating local models and saving forecasts | `COMPLETED`, `FAILED` |
| `COMPLETED` | Finished; counts and timestamps are stored | Terminal |
| `FAILED` | Error recorded; retry may be scheduled | `QUEUED` |

Every transition is validated in the service and appended to `job_transitions` with the attempt number, timestamp, and reason. `analysis_jobs` keeps the current state, result counts, latest error, retry availability, timestamps, and attempt ownership token. Clients can request jobs or retry failed ones; they cannot assign arbitrary states.

## Scheduling and execution

- Startup queues rate history, news history, and recent news jobs. Existing pending work of the same type is reused.
- The daily schedules enqueue rate and recent-news jobs as before.
- A background worker polls the durable queue every five seconds. The local API enables this worker by default.
- CLI collectors and the analysis command use the same queue and state machine.
- The Next.js panel offers rate refresh, recent news, news backfill, and analysis-only tasks. It polls every five seconds, shows state history and failures, and refreshes the dashboard data after a task completes.

Each job type has at most one pending/running/retry-waiting job, enforced by a unique active key and a transactional enqueue lock. Queued jobs are claimed using row locking. A dedicated PostgreSQL connection holds an exclusive worker advisory lock across stage commits, so competing worker processes cannot run the pipeline simultaneously.

## Failure and restart recovery

An attempt that fails records its error and transitions to `FAILED`. Up to three automatic attempts are allowed, with 30-second and 60-second retry delays. Exhausted jobs stay failed until **Retry now** is selected. A manual retry of an exhausted job grants one additional attempt, preserving all previous history.

After a worker process dies, PostgreSQL releases its worker lock when its connection closes. The next worker acquires that lock before treating any persisted in-progress attempt as interrupted. It records the failure and requeues it immediately if attempts remain. A live worker is never reclaimed merely because a collection takes a long time. Attempt tokens also prevent an older attempt from overwriting a recovered attempt's state.

Retries start the pipeline again. This is at-least-once execution: data already committed before a crash can be processed again. Rate/article upserts and deduplicated derived events/alerts make that replay safe. Existing seven-day news batch commits are preserved. A bounded final failure remains visible instead of retrying forever.

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/jobs/collection` | Queue a job; returns HTTP 202 immediately |
| `GET /api/v1/jobs?limit=10` | Recent jobs and their current states |
| `GET /api/v1/jobs/{id}` | Current state, results, and complete transition history |
| `POST /api/v1/jobs/{id}/retry` | Requeue a failed job; 409 if it cannot be retried |

Request body example: `{"job_type": "rates"}`. Supported types are `rates`, `news_recent`, `news_history`, `analysis`, and `forecast`. Next.js forwards these through its same-origin `/api/jobs` routes.

## Run and migrate

From `project/backend`:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --reload-dir app
```

For a separate worker process, set `JOB_WORKER_ENABLED=false` in the backend `.env`, restart the API, and run:

```powershell
.\.venv\Scripts\python.exe -m app.workers.run_jobs
```

The API still queues startup and scheduled work when its embedded worker is disabled. The independent worker handles execution and recovery. `--once` drains currently ready jobs and exits; `--job analysis --once` queues and processes an analysis job. Future retries need a running worker. Keep one API scheduler instance to avoid redundant daily scheduling; the database locks still protect execution across competing workers.

## Verification

- 60 backend tests pass, including legal transitions, complete pipeline history, bounded retries/backoff, interrupted-attempt recovery, stale-owner rejection, worker exclusion, deduplicated submissions, and manual retry history.
- Migration `b271cd904e12` was applied to the actual PostgreSQL database; Alembic detects no model/schema drift.
- Actual rate and news jobs completed through the persisted stages.
- A worker process was deliberately terminated mid-attempt. The live scheduler recorded `FAILED`, requeued it, and completed attempt two without manual database repair. A concurrent request reused the same queued job while the worker lock was held.
- A real Edge browser submitted analysis from Next.js, observed completion and transition history, retried a failed job successfully, and checked desktop/mobile layout widths.
- Existing stored rates, moving averages, relevance scores, and pair/window API checks continue to pass the market audit.

Forecast jobs use the same worker lock, attempt tokens, retry limits, and crash recovery. The Forecast panel queues training for all eight KRW pairs. After the first saved forecast, completed rate/recent-news jobs enqueue forecast refreshes. News collection also extracts local evidence. The extended suite passes 70 tests. See [local forecasting](news-forecasting.md).
