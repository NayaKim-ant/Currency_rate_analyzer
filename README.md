# 환율·뉴스 분석 서비스

저장소는 문서와 실행 프로젝트를 분리한다. 문서는 `docs/`에, 서비스 코드는 `project/`에 둔다. `project/` 안에는 FastAPI/PostgreSQL backend와 Next.js frontend의 자리, 그리고 비교용 기존 프로토타입이 있다.

## 시작하기

신규 backend 실행 (저장소 루트에서):

```powershell
cd project/backend
.\.venv\Scripts\Activate.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-postgres.ps1
alembic upgrade head
uvicorn app.main:app --reload --reload-dir app
```

처음 설치할 때의 Python 환경 및 PostgreSQL 준비는 [backend 안내](project/backend/README.md)를 참고한다. 별도 터미널에서 `project/frontend`로 이동해 `npm.cmd run dev`를 실행하고 `http://localhost:3000`을 연다. API 주소는 `http://127.0.0.1:8000`이다. 앱 시작 시 데이터 수집과 분석을 실행하며, 기존 데이터는 PostgreSQL에 유지된다.

비교용 기존 프로토타입 실행:

```powershell
python -m software_architecture.project.legacy.process_and_thread
```

명령은 `software_architecture/` 저장소 폴더의 상위 디렉터리에서 실행한다. legacy 프로그램에는 Node.js가 필요하다. 신규 앱은 `project/backend/`와 `project/frontend/`에 있으며 각 README에 실행 방법을 적었다. PostgreSQL 서버는 별도로 준비해야 한다.

## 문서

- [Job 상태 머신](docs/job-state-machine.md): 작업 상태·전이 이력, 실패/retry, crash recovery, Next.js 진행 표시와 별도 worker 실행
- [구현 검증 결과](docs/verification.md): 현재 실행 구조, legacy 비교, 시계열 계산 및 dashboard 연동 검증
- [구현 계획](docs/implementation-plan.md): FastAPI·PostgreSQL·Python worker·Next.js 전환 단계와 기능 범위
- [코드베이스 분석 가이드](docs/codebase-guide.md): 파일별 책임, 호출 흐름, 메시지/큐, 상태, 알려진 한계
- [시스템 아키텍처](docs/architecture.md): 프로세스와 워커 구성
- [데이터 흐름](docs/data-flow.md): 수집부터 종료까지의 시퀀스
- [데이터 구조](docs/data-structure.md): Python 메시지, IPC JSON, 파일 스키마

## 주요 소스

| 경로 | 역할 |
|---|---|
| `project/backend/` | FastAPI, PostgreSQL 모델/서비스, 수집·분석 worker의 목표 위치 |
| `project/frontend/` | Next.js App Router dashboard의 목표 위치 |
| `project/legacy/process_and_thread.py` | 기존 프로토타입 실행 및 전체 생명주기 조립 |
| `project/legacy/thread_worker.py` | 기존 환율·뉴스 수집 및 기사 분석 |
| `project/legacy/ipc_handler.py` | 기존 Python TCP IPC 서버 |
| `project/legacy/node_process.js` | 기존 Node 분석 및 인사이트 저장 |

기존 프로토타입의 JSON 결과는 `project/legacy/`에 생성된다. 디렉터리별 역할은 [프로젝트 구조 안내](project/README.md)와 각 영역의 README를 참고한다.

## Experimental local forecasting

The Forecast section compares a local LSTM and news-aware candidate with a no-change baseline, in KRW per foreign unit. See [setup, evaluation, and current limitations](docs/news-forecasting.md). No paid API or LLM key is needed.

Historical imports: [archive backfill and evaluation timing](docs/historical-data.md). Explicit date ranges expand stored rates/news without increasing daily startup lookbacks.
