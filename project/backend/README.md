# Backend

FastAPI와 PostgreSQL을 사용하는 Python backend 영역이다. API 요청 처리와 도메인 로직은 `app/`에 두고, 장시간 수집·분석은 독립 실행 가능한 `app/workers/` 모듈로 둔다.

The default base currency is now KRW, with USD as the default foreign target. Stored/default API rates are foreign currency units per 1 KRW. The dashboard requests `quote_direction=base_per_target`, which returns the KRW cost of one foreign unit. Daily observations are inverted before recalculating moving averages and trend state. The response identifies `rate_currency` and `unit_currency`. Lower chart values mean fewer won are needed to buy the selected currency. Articles, events, and alerts are filtered by base and target currency so previous USD-base results stay separate.

KRW rates are calculated with Decimal arithmetic from the provider's USD quotes (`foreign per USD / KRW per USD`), avoiding the loss of precision in directly rounded KRW-base quotes. To initialize missing KRW history and score existing articles without fetching them again, run `python -m app.workers.rebase_krw`. Existing USD history remains available through explicit `base_currency=USD` queries. No schema migration is required.

## 구조

Background collection/analysis now runs through a persistent PostgreSQL job state machine. Apply the migration with `python -m alembic upgrade head` before restarting the API. Startup, daily schedules, and CLI collectors use the same queue. The API's default background worker checks it every five seconds; Next.js shows states, attempts, results, failures, retry controls, and transition history under **Background logs**. See [state-machine guide](../../docs/job-state-machine.md).

Jobs follow `QUEUED -> COLLECTING -> ANALYZING -> EVALUATING_ALERTS -> COMPLETED`, with failures recorded as `FAILED`. Analysis-only jobs skip collection. Automatic retries are limited to three attempts; interrupted work is recovered once the old worker's database lock is released. Repeated requests reuse pending work of the same type.

To run execution in a separate process, set `JOB_WORKER_ENABLED=false` in `.env`, restart the API, and run `python -m app.workers.run_jobs` in another terminal. Use `--once` to process currently ready work and exit. The existing collection/analysis CLI commands now print a job ID whose status/results are available at `/api/v1/jobs/{id}`.

```text
backend/
  app/
    api/v1/       버전이 지정된 HTTP endpoint와 router
    core/         설정, 공통 예외 및 보안 설정
    db/           SQLAlchemy 엔진, 세션, Base
    models/       PostgreSQL ORM 모델
    schemas/      API 요청/응답 Pydantic 스키마
    services/     환율·기사·추세·알림 도메인 로직
    workers/      데이터 수집 및 분석 작업 진입점
  migrations/     Alembic 설정과 버전 파일
  tests/          backend 테스트
```

현재 FastAPI 앱에는 `/health`, 환율·기사·이벤트·alert 조회 API가 있고, 환율·기사·관련도·추세·이벤트·alert용 ORM 모델 및 Alembic revision이 있다. 앱 시작 시 최근 365일 환율과 최근 90일 RSS 요약을 background catch-up job으로 동기화한다. 뉴스는 7일 구간마다 DB에 commit하고, 최근 7일은 본문도 수집한다. 앱이 실행 중이면 서울 시간 매일 06:00에 환율을, 06:20에 최근 7일 뉴스를 재수집한다.

앱을 종료한 동안에는 scheduler가 돌지 않는다. 다음 실행 때 설정된 lookback 기간을 다시 동기화하므로 중단 중 빠진 구간을 보충한다. PostgreSQL이 실행 중이고 `.env` 접속 정보와 migration이 준비되어야 한다. 초기 동기화 실패는 로그에 남으며 API는 계속 제공한다. `/health`는 API 생존 상태이지 DB 준비 상태를 보장하지 않는다.

Frankfurter가 반환하는 영업일 관측값을 전 기간 재조회한다. 주말·시장 휴일은 원천에 값이 없으므로 누락 데이터로 취급하지 않는다. 뉴스는 Google News RSS의 주간 검색 구간을 훑고 URL 기준으로 중복을 제거하지만, 검색 공급자의 과거 기사 보존/노출 한계 때문에 환율 시계열처럼 완전성을 보장할 수는 없다.

## 로컬 실행

backend 디렉터리에서 실행한다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Portable PostgreSQL 설치와 시작은 backend 디렉터리에서 수행한다:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install-postgres-portable.ps1
.\scripts\start-postgres.ps1
```

이 개발용 설치는 PostgreSQL을 `127.0.0.1`에만 바인딩하고 Windows 서비스나 관리자 권한 없이 실행한다. 데이터는 `%LOCALAPPDATA%\BasisMarket\PostgreSQL\data`에 남는다. localhost trust 인증은 로컬 개발 전용이며 네트워크에 공개하지 않는다.

DB가 실행 중일 때 `.env`의 `DATABASE_URL`을 확인하고 migration을 적용한다. 기본값은 portable 설정에 맞춰져 있다:

```powershell
alembic upgrade head
uvicorn app.main:app --reload --reload-dir app
```

FastAPI는 응답을 시작한 뒤 catch-up job을 실행한다. PC나 앱이 꺼져 있는 동안에는 수집되지 않지만, 다음 실행 때 365일 환율과 90일 RSS 요약을 다시 확인한다. 주말·시장 휴일은 환율 원천에 값이 없는 정상 구간이다. RSS의 과거 기사 노출 범위는 공급자 한계가 있다.

health check: `http://127.0.0.1:8000/health`

확인이 끝나면 `scripts\stop-postgres.ps1`로 DB 프로세스만 종료할 수 있다. 이후에도 data directory는 삭제하지 않는 한 유지된다.

보통은 backend 시작 시 catch-up이 자동 실행된다. 수동으로 다시 실행할 때:

```powershell
python -m app.workers.collect_rates
```

뉴스 수집과 기사 관련도 적재:

```powershell
python -m app.workers.collect_news
```

Alert 규칙 평가:

```powershell
python -m app.workers.evaluate_alerts
```

Celery, Redis, RabbitMQ와 관측성 시스템은 사용하지 않는다. scheduler는 API 프로세스 안에서 동작하므로 Uvicorn worker를 여러 개로 띄우지 않는다.

## Persisted analysis

### Won-price alerts

The dashboard supports `won_cost_at_or_below` and `won_cost_at_or_above` targets, measured in KRW per one foreign unit (for example, 1 USD at or below KRW 1,300). Rules require a KRW base and a supported foreign target. They evaluate the reciprocal of the latest stored rate and can work with a single collected quote.

Creating or resuming a rule checks it immediately. Rate collection also evaluates enabled rules. One occurrence is recorded per rule/type/quote date; repeated checks do not duplicate it. These use daily reference quotes, and occurrence dates identify the source quote date.

`POST /api/v1/alerts/rules` creates a rule; `GET /api/v1/alerts/rules` accepts optional base/target filters. `PATCH /api/v1/alerts/rules/{id}` with `{"enabled": false}` pauses a rule (`true` resumes it). `DELETE` on that path removes the rule and preserves occurrence history. `POST /api/v1/alerts/evaluate` checks the latest stored quotes. Dashboard requests go through the Next.js same-origin `/api/alerts` routes. Notifications appear in the dashboard, which refreshes its alert panel every 30 seconds.

Verified: 51 backend tests pass. A real browser exercised create/trigger/pause/resume/delete and checked desktop/mobile layout; temporary rules and occurrences were removed afterward.

Collectors refresh trend snapshots, price and reversal events, policy article links, and enabled alert rules. To analyze stored data without collecting again:

```powershell
python -m app.workers.analyze_market
```

`GET /api/v1/trends` returns the latest snapshot per currency and its calculation criteria. Filter with `target_currency` and `base_currency`. The baseline change-point threshold is an absolute daily change of at least 2%. Policy article links use a two-day window and indicate temporal association. The `change_point_candidate` alert type uses the rule's configured threshold. Trend reversal values are MA5 minus MA20, measured in rate units.

Repeated analysis reuses snapshots by currency pair/date and events by pair/type/date/article, and removes generated timeline events invalidated by source corrections. PostgreSQL transaction locks serialize news, analysis, and alert writes. Data persists across PostgreSQL restarts.

Verified 2026-10-16: 32 backend tests passed. A clean DB restart retained 2,032 rates, 110 articles, 2,032 snapshots, and 119 events. Repeated analysis created zero additional events. The 90-day news worker completed, but RSS provider coverage does not guarantee a complete historical archive.

Final audit: 36 backend tests passed. All 248 archived legacy rates and eight legacy MA5/daily-change results matched. All 6,096 stored moving averages and 24 currency/display-window combinations passed verification. Run `python scripts/verify_market.py` to repeat the read-only audit. See [verification report](../../docs/verification.md).

Rate query `days` controls the visible calendar range; calculations include earlier observations for complete averages. Article windows use publication dates, with collection dates as the fallback for undated articles. Alert `lookback_days` uses calendar days and the latest quote on or before its baseline date.

## Local forecasting

Optional CPU ML dependencies live in `requirements-ml.txt`. Forecast jobs extract source evidence and train all eight currencies through `QUEUED -> EXTRACTING_HINTS -> FORECASTING -> COMPLETED`. After the first saved run, rate/recent-news jobs enqueue refreshes. See [forecasting guide](../../docs/news-forecasting.md) for setup, point-in-time evidence rules, baseline gates, and real-data limitations. Latest suite: 70 tests passed.

Historical imports: [archive backfill and evaluation timing](../../docs/historical-data.md). Explicit date ranges expand stored rates/news without increasing daily startup lookbacks.
