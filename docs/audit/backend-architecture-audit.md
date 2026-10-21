# Backend (`project/backend/app`) 구조 전수조사 및 아키텍처 개선 검토 보고서

**작성일**: 2026-10-21  
**대상 경로**: `project/backend/app/`  
**상태**: 검토 완료 (리팩토링 제안 문서)

---

## 1. 개요 및 감사 목적

`project/backend/app`은 FastAPI 기반의 백엔드 서비스로, 환율 수집, 뉴스 크롤링, 거시경제 팩트 추출, 시계열 머신러닝 예측(LSTM/Ridge/GBDT), 알림 평가, PostgreSQL 상태 머신 기반 작업 큐 등 다양한 도메인 로직을 포함하고 있습니다.

현재 최상위 레이어(`api/`, `core/`, `db/`, `models/`, `schemas/`, `services/`, `workers/`)는 표준적인 FastAPI 계층 구조를 따르고 있으나, 프로젝트의 기능이 지속적으로 확장됨에 따라 **일부 디렉토리에 16개 이상의 파일이 평면적으로 집중**되어 있거나, **하나의 파일에 8개의 도메인 모델이 몰려 있는(God File)** 등의 구조적 병목이 확인되었습니다.

본 문서는 `app/` 하위 전체 파일에 대한 전수조사 결과를 바탕으로, **기능별 파일 분류 적합성 평가**, **문제점 분석**, 그리고 **1-Depth 서브패키지화 및 경로 재분류 방안**을 제시합니다.

---

## 2. `app/` 하위 전체 파일 현황 전수조사 (Total Inventory)

| 경로 | 파일명 | 크기 / 라인 수 | 주요 책임 및 역할 |
|---|---|---|---|
| `app/` | `main.py` | 1.9 KB / 62 lines | FastAPI 앱 생성, CORS 설정, 라이프스팬(`APScheduler` 초기화), 라우터 등록 |
| `app/core/` | `config.py` | 0.8 KB / 24 lines | Pydantic 기반 환경변수 설정 (`DATABASE_URL`, CORS 등) |
| `app/core/` | `currencies.py` | 0.2 KB / 10 lines | 지원 통화 목록(`FOREIGN_CURRENCIES`, `HOME_CURRENCY`) 상수 |
| `app/db/` | `base.py` | 0.1 KB / 4 lines | SQLAlchemy 2.0 `DeclarativeBase` |
| `app/db/` | `session.py` | 0.5 KB / 18 lines | DB 엔진 생성, 세션 팩토리(`SessionLocal`), FastAPI 세션 의존성(`get_db`) |
| `app/db/` | `locks.py` | 0.5 KB / 17 lines | PostgreSQL 전역 쓰기 Advisory Lock 함수 (`lock_market_writes`) |
| `app/models/` | `market.py` | 7.1 KB / 146 lines | **(과밀)** `ExchangeRate`, `Article`, `ArticleKeyword`, `ArticleRelevance`, `TrendSnapshot`, `MarketEvent`, `AlertRule`, `AlertEvent` (총 8개 모델) |
| `app/models/` | `forecasts.py` | 3.0 KB / 56 lines | `NewsFact`, `ForecastRun`, `ForecastOutcome` |
| `app/models/` | `jobs.py` | 2.5 KB / 45 lines | `AnalysisJob`, `JobTransition` |
| `app/schemas/` | `rates.py` | 0.6 KB / 26 lines | 환율 시계열 조회 응답 스키마 (`RatePoint`, `RateSeriesResponse`) |
| `app/schemas/` | `articles.py` | 0.3 KB / 14 lines | 기사 검색 결과 스키마 (`ArticleSearchResult`) |
| `app/schemas/` | `alerts.py` | 1.4 KB / 46 lines | 알림 규칙 생성/조회/수정 스키마 (`AlertRuleCreate`, `AlertRuleRead` 등) |
| `app/schemas/` | `jobs.py` | 0.9 KB / 32 lines | 작업 큐 상태 조회 스키마 (`JobRead`, `JobTransitionRead`) |
| `app/api/v1/` | `rates.py` | 3.1 KB / 78 lines | 환율 조회 및 라우터 내 직접 이동평균/추세 계산 API |
| `app/api/v1/` | `articles.py` | 2.5 KB / 63 lines | 뉴스 기사 및 관련도 점수 조회 API |
| `app/api/v1/` | `trends.py` | 1.7 KB / 39 lines | 통화별 최신 추세 스냅샷 조회 API (Pydantic 스키마 누락) |
| `app/api/v1/` | `events.py` | 1.6 KB / 46 lines | 시장 타임라인 이벤트 조회 API (Pydantic 스키마 누락) |
| `app/api/v1/` | `alerts.py` | 3.9 KB / 99 lines | 알림 규칙 CRUD 및 발생 내역 조회 API |
| `app/api/v1/` | `forecasts.py` | 3.4 KB / 57 lines | 예측 결과, 힌트, 스코어카드, 매수 타이밍 조회 API |
| `app/api/v1/` | `jobs.py` | 1.7 KB / 50 lines | 작업 상태 머신 조회, 재시도 트리거 API |
| `app/services/` | `collection.py` | 5.1 KB / 122 lines | Frankfurter API 호출 및 환율 데이터 DB 적재 |
| `app/services/` | `trends.py` | 0.9 KB / 31 lines | 단순 이동평균(MA) 계산 및 골든/데드크로스 추세 분류 함수 |
| `app/services/` | `signals.py` | 3.0 KB / 78 lines | 급등락(`rapid_rise/fall`), 추세 반전 감지 순수 로직 |
| `app/services/` | `analysis.py` | 5.5 KB / 102 lines | 이동평균 스냅샷 및 마켓 이벤트 생성 종합 오케스트레이션 |
| `app/services/` | `news.py` | 9.9 KB / 272 lines | Google News RSS 파싱, HTML 본문 크롤링, 기사 DB 적재 |
| `app/services/` | `relevance.py` | 2.2 KB / 68 lines | 정규식 기반 통화/정책 키워드 매칭 및 기사 연관도 산출 |
| `app/services/` | `news_facts.py` | 7.6 KB / 135 lines | 뉴스 본문 내 6대 경제 요인(금리, 물가 등) 팩트 추출 |
| `app/services/` | `economic_events.py` | 3.4 KB / 57 lines | 문장 단위 경제 지표 수치(이전치, 기대치, 서프라이즈) 파싱 |
| `app/services/` | `alert_engine.py` | 6.7 KB / 144 lines | 등록된 알림 규칙 조건 검사 및 알림 이벤트 발송 처리 |
| `app/services/` | `forecasting.py` | 17.2 KB / 307 lines | 시계열 데이터셋 구축, PyTorch LSTM 학습 및 챔피언 선발 |
| `app/services/` | `simple_forecasters.py` | 1.2 KB / 28 lines | Ridge 회귀 및 Gradient Boosting Regressor 학습/추론 |
| `app/services/` | `forecast_scorecard.py` | 9.3 KB / 162 lines | 사후 정산(Settlement), 전진 스코어카드 누적 및 게이트 평가 |
| `app/services/` | `purchase_outlook.py` | 2.4 KB / 39 lines | 오차 범위 기반 외화 매수 타이밍 휴리스틱 신호 도출 |
| `app/services/` | `jobs.py` | 6.0 KB / 148 lines | DB 작업 큐 상태 머신 정의, 상태 전이, 큐잉(`claim_job` 등) |
| `app/services/` | `job_runner.py` | 6.6 KB / 154 lines | Advisory Lock 기반 단일 워커 가드, 파이프라인 단계별 실행 |
| `app/services/` | `scheduler.py` | 1.8 KB / 49 lines | APScheduler 스케줄 설정 (06:00 환율, 06:20 뉴스, 5초 주기 큐) |
| `app/workers/` | `run_jobs.py` | 1.0 KB / 34 lines | 파이프라인 큐 처리 메인 루프 워커 데몬 CLI |
| `app/workers/` | `collect_rates.py` | 0.1 KB / 10 lines | `run_requested("rates")` 호출 래퍼 CLI |
| `app/workers/` | `collect_news.py` | 0.2 KB / 11 lines | `run_requested("news_history/recent")` 호출 래퍼 CLI |
| `app/workers/` | `analyze_market.py` | 0.1 KB / 10 lines | `run_requested("analysis")` 호출 래퍼 CLI |
| `app/workers/` | `evaluate_alerts.py` | 0.3 KB / 13 lines | `evaluate_alert_rules()` 직접 실행 CLI |
| `app/workers/` | `rebase_krw.py` | 2.2 KB / 52 lines | 과거 USD 기준 환율을 KRW 교차 환율로 재계산/변환하는 배치 스크립트 |
| `app/workers/` | `backfill_archive.py` | 4.1 KB / 85 lines | 과거 특정 기간 환율 및 뉴스를 대량 가져오는 아카이브 백필 CLI 도구 |

---

## 3. 세부 파일별 기능 및 네이밍 적합성 평가

### (1) 적합하지 않거나 개선이 필요한 파일/기능 분석

| 파일명 | 현재 위치 | 발견된 문제점 및 부적합 요소 | 권장 조치 |
|---|---|---|---|
| `market.py` | `app/models/` | **God Model 파일**: 환율, 뉴스 기사, 연관도, 추세, 이벤트, 알림 등 성격이 다른 8개의 모델이 1개 파일에 모두 정의되어 결합도가 지나치게 높음. | 도메인별 분리 (`rates.py`, `news.py`, `alerts.py`) |
| `forecasts.py` | `app/models/` | `NewsFact` 모델이 예측 파일에 위치함. 실제로는 기사 본문(`Article`)을 파싱한 NLP 팩트 엔티티이므로 예측과 뉴스 도메인 경계가 모호함. | `NewsFact`를 뉴스 도메인 모델로 재분류하거나 명확한 외래키 관계 정리 |
| `collection.py` | `app/services/` | **네이밍 모호성**: 파일명은 단순히 '수집'이지만 실제로는 **환율(Frankfurter API)**만 수집함. 뉴스는 `news.py`에서 별도로 수집하고 있어 혼란 유발. | `rates_collector.py` 또는 `rates/collector.py`로 명확화 |
| `services/` 전체 | `app/services/` | **16개 파일의 평면적 과밀화**: 환율 분석, 뉴스 크롤링, NLP 팩트 추출, ML 예측, 알림 엔진, 작업 큐 상태 머신, 스케줄러가 한 디렉토리에 혼재되어 도메인 구분이 안 됨. | 하위에 **1-Depth 도메인 서브패키지** 구성 필요 |
| `rates.py` | `app/api/v1/` | **비즈니스 로직 누수 (Fat Controller)**: 라우터 함수 내부에서 웜업 데이터 슬라이싱, 역수 계산, 이동평균 호출, 추세 판별 로직을 직접 수행함. | 서비스 레이어로 로직 이관 |
| `forecasts.py` | `app/api/v1/` | **라우터 내 과도한 가공 로직**: 뉴스 힌트 중복 제거, stale 여부 판정 등의 복잡한 계산이 엔드포인트 핸들러에 직접 작성됨. | `purchase_outlook` 또는 전용 서비스로 캡슐화 |
| `trends.py`, `events.py` | `app/api/v1/` | **Pydantic 스키마 부재**: 응답 타입이 `list[dict[str, object]]`로 되어 있어 Swagger 문서가 불완전하고 타입 안정성이 결여됨. | `schemas/`에 전용 Response 모델 정의 |
| `evaluate_alerts.py` | `app/workers/` | **실행 일관성 결여**: 다른 워커 스크립트(`collect_rates`, `collect_news`)는 `run_requested()`를 통해 DB 큐를 타지만, 이 스크립트만 DB 세션을 열어 직접 실행함. | 파이프라인 큐 방식으로 통일하거나 CLI 툴로 분류 |
| `rebase_krw.py`, `backfill_archive.py` | `app/workers/` | **책임 혼재**: 지속적 백그라운드 워커가 아니라, 1회성 마이그레이션 및 수동 아카이브 적재용 '유지보수 CLI 스크립트'임에도 `workers/`에 공존함. | `cli/` 또는 `scripts/`로 분리 |

---

## 4. 구조 개선 및 1-Depth 도입 방안 (Proposed Reorganization)

가장 추천하는 구조는 **기존 FastAPI 계층형 구조(API, Models, Schemas, Services, Workers)를 유지하면서, 비대해진 영역에 1-Depth의 도메인별 서브패키지를 구성하는 방식**입니다.

### 4.1 권장 디렉토리 구조도

```text
project/backend/app/
├── api/
│   └── v1/
│       ├── rates.py
│       ├── articles.py
│       ├── trends.py
│       ├── events.py
│       ├── alerts.py
│       ├── forecasts.py
│       └── jobs.py
│
├── core/
│   ├── config.py
│   └── currencies.py
│
├── db/
│   ├── base.py
│   ├── session.py
│   └── locks.py
│
├── models/                     <-- [개선] 도메인별 1-Depth 분리
│   ├── __init__.py             (하위 호환성 위해 모든 모델 re-export)
│   ├── rates.py                (ExchangeRate, TrendSnapshot, MarketEvent)
│   ├── news.py                 (Article, ArticleKeyword, ArticleRelevance, NewsFact)
│   ├── alerts.py               (AlertRule, AlertEvent)
│   ├── forecasts.py            (ForecastRun, ForecastOutcome)
│   └── jobs.py                 (AnalysisJob, JobTransition)
│
├── schemas/                    <-- [개선] 누락된 스키마 보충
│   ├── rates.py
│   ├── articles.py
│   ├── trends.py               (신규: TrendSnapshotResponse)
│   ├── events.py               (신규: MarketEventResponse)
│   ├── alerts.py
│   ├── forecasts.py            (신규: ForecastResponse, OutlookResponse)
│   └── jobs.py
│
├── services/                   <-- [핵심 개선] 16개 파일을 5개 도메인으로 1-Depth 패키지화
│   │
│   ├── rates/                  # 1. 환율 수집 및 시계열 분석 도메인
│   │   ├── __init__.py
│   │   ├── collector.py        (구 collection.py: Frankfurter 환율 수집)
│   │   ├── trends.py           (구 trends.py: MA 및 추세 계산)
│   │   ├── signals.py          (구 signals.py: 급등락/반전 시그널)
│   │   └── analyzer.py         (구 analysis.py: 스냅샷 및 마켓 이벤트 종합 분석)
│   │
│   ├── news/                   # 2. 뉴스 수집 및 자연어 팩트 추출 도메인
│   │   ├── __init__.py
│   │   ├── collector.py        (구 news.py: Google News RSS 수집 및 크롤링)
│   │   ├── relevance.py        (구 relevance.py: 통화/정책 연관도 점수)
│   │   ├── facts.py            (구 news_facts.py: 6대 거시경제 팩트 추출)
│   │   └── events.py           (구 economic_events.py: 지표 수치/서프라이즈 파싱)
│   │
│   ├── forecasting/            # 3. 시계열 머신러닝 예측 도메인
│   │   ├── __init__.py
│   │   ├── engine.py           (구 forecasting.py: 데이터셋 빌드, PyTorch LSTM 학습)
│   │   ├── simple_models.py    (구 simple_forecasters.py: Ridge, Boosted Trees)
│   │   ├── scorecard.py        (구 forecast_scorecard.py: 전진 검증 스코어카드 및 사후정산)
│   │   └── outlook.py          (구 purchase_outlook.py: 매수 타이밍 신호)
│   │
│   ├── alerts/                 # 4. 알림 규칙 평가 도메인
│   │   ├── __init__.py
│   │   └── engine.py           (구 alert_engine.py: 알림 규칙 평가 및 이벤트 발송)
│   │
│   └── pipeline/               # 5. 작업 큐 및 스케줄러 인프라 도메인
│       ├── __init__.py
│       ├── state_machine.py    (구 jobs.py: 작업 상태 정의, 큐잉, 전이 로직)
│       ├── runner.py           (구 job_runner.py: 워커 락, 작업 실행 및 복구)
│       └── scheduler.py        (구 scheduler.py: APScheduler 설정)
│
├── workers/                    <-- [개선] 지속 구동 큐 데몬 및 파이프라인 트리거
│   ├── run_jobs.py             (상시 구동 파이프라인 큐 워커)
│   └── dispatchers.py          (구 collect_rates, collect_news, analyze_market을 통합하거나 유지)
│
└── cli/                        <-- [신규] 1회성 데이터 마이그레이션 / 관리자 배치 도구
    ├── __init__.py
    ├── rebase_krw.py           (구 workers/rebase_krw.py: KRW 교차환율 재산출)
    └── backfill_archive.py     (구 workers/backfill_archive.py: 대량 과거 데이터 백필)
```

---

## 5. 변경 대상 파일 매핑표 (Before -> After Mapping)

### (1) `services/` 서브패키지화
| 기존 파일 경로 | 신규 변경 경로 | 분류 사유 |
|---|---|---|
| `app/services/collection.py` | `app/services/rates/collector.py` | 환율 API 호출 및 저장 전담 |
| `app/services/trends.py` | `app/services/rates/trends.py` | 환율 이동평균 및 추세 상태 분류 |
| `app/services/signals.py` | `app/services/rates/signals.py` | 환율 급등락 및 골든/데드크로스 감지 |
| `app/services/analysis.py` | `app/services/rates/analyzer.py` | 환율 시계열 스냅샷 및 시장 이벤트 종합 생성 |
| `app/services/news.py` | `app/services/news/collector.py` | Google News RSS 파싱 및 기사 본문 수집 |
| `app/services/relevance.py` | `app/services/news/relevance.py` | 기사 키워드 및 통화 연관도 점수 산출 |
| `app/services/news_facts.py` | `app/services/news/facts.py` | 기사 본문 내 6대 경제 요인 팩트 추출 |
| `app/services/economic_events.py` | `app/services/news/events.py` | 문장 내 거시 지표 수치 및 기대치 서프라이즈 파싱 |
| `app/services/forecasting.py` | `app/services/forecasting/engine.py` | 시계열 데이터셋 구축, PyTorch LSTM 학습 및 챔피언 선발 |
| `app/services/simple_forecasters.py` | `app/services/forecasting/simple_models.py` | Ridge 회귀 및 GBDT 부스팅 트리 학습/추론 |
| `app/services/forecast_scorecard.py` | `app/services/forecasting/scorecard.py` | 사후 정산(Settlement) 및 30일 전진 검증 스코어카드 |
| `app/services/purchase_outlook.py` | `app/services/forecasting/outlook.py` | 오차 범위 기반 외화 매수 타이밍 신호 도출 |
| `app/services/alert_engine.py` | `app/services/alerts/engine.py` | 알림 규칙 평가 및 이벤트 발송 |
| `app/services/jobs.py` | `app/services/pipeline/state_machine.py` | DB 큐 상태 머신 정의 및 큐잉 |
| `app/services/job_runner.py` | `app/services/pipeline/runner.py` | 단일 워커 Advisory Lock 및 파이프라인 단계별 실행 |
| `app/services/scheduler.py` | `app/services/pipeline/scheduler.py` | APScheduler 백그라운드 스케줄러 등록 |

### (2) `models/` 도메인별 분리
| 기존 파일 경로 | 모델 클래스 | 신규 변경 경로 |
|---|---|---|
| `app/models/market.py` | `ExchangeRate`, `TrendSnapshot`, `MarketEvent` | `app/models/rates.py` |
| `app/models/market.py` | `Article`, `ArticleKeyword`, `ArticleRelevance` | `app/models/news.py` |
| `app/models/forecasts.py` | `NewsFact` | `app/models/news.py` (또는 유지) |
| `app/models/market.py` | `AlertRule`, `AlertEvent` | `app/models/alerts.py` |
| `app/models/forecasts.py` | `ForecastRun`, `ForecastOutcome` | `app/models/forecasts.py` |
| `app/models/jobs.py` | `AnalysisJob`, `JobTransition` | `app/models/jobs.py` |

### (3) `workers/` 관리자 스크립트 분리
| 기존 파일 경로 | 신규 변경 경로 | 분리 사유 |
|---|---|---|
| `app/workers/rebase_krw.py` | `app/cli/rebase_krw.py` | 1회성 데이터 변환/마이그레이션 스크립트 |
| `app/workers/backfill_archive.py` | `app/cli/backfill_archive.py` | 파라미터 기반 대량 과거 데이터 백필 CLI 도구 |
| `app/workers/evaluate_alerts.py` | `app/cli/evaluate_alerts.py` | 큐를 거치지 않는 수동 점검용 CLI 스크립트 |

---

## 6. 리팩토링 시 주의사항 및 마이그레이션 가이드라인

1. **Alembic 모델 탐색 (`env.py`) 및 외래키 호환성**:
   * `app/models/__init__.py`에서 모든 모델(`ExchangeRate`, `Article`, `AlertRule` 등)을 `import`하여 re-export하도록 구성하면, 기존 `from app.models.market import ...` 구문과의 하위 호환성을 유지할 수 있고 Alembic schema drift가 발생하지 않습니다.
2. **`services/__init__.py`의 Facade / Re-export 패턴 적용**:
   * 서비스를 서브패키지로 옮기더라도, 기존 외부 호출 코드나 테스트 코드가 깨지지 않도록 주요 함수(`drain_jobs`, `enqueue_job`, `train_forecasts`, `analyze_market` 등)를 상위 패키지에서 re-export하는 점진적 전환을 권장합니다.
3. **순환 참조(Circular Import) 방지**:
   * `services/pipeline/runner.py`가 각 도메인 서비스(`rates`, `news`, `forecasting`, `alerts`)를 호출하므로, 하위 도메인 서비스가 다시 `pipeline/runner.py`를 참조하지 않도록 의존성 방향을 단방향(Top-down)으로 명확히 유지해야 합니다.
4. **테스트 스위트 검증**:
   * 파일 이동 후 기존 95개 이상의 Pytest 단위/통합 테스트가 수정 없이(또는 import 경로만 갱신하여) 모두 정상 통과하는지 회귀 검증을 수행해야 합니다.
