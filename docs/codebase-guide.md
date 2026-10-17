# 코드베이스 분석 가이드

이 문서는 `project/legacy/`에 보존된 프로토타입 소스 코드가 어떻게 연결되어 동작하는지 파일별로 읽을 수 있도록 정리한다. 전체 구성과 데이터 계약은 각각 [아키텍처](architecture.md), [데이터 흐름](data-flow.md), [데이터 구조](data-structure.md)를 참고한다.

## 한눈에 보는 실행 모델

프로그램은 Python과 Node.js 두 프로세스로 구성된다. 각 프로세스의 스레드는 역할별 큐/이벤트 채널을 사용하며, 서로 다른 프로세스 사이에서는 localhost TCP를 사용한다.

```text
python -m software_architecture.project.legacy.process_and_thread
│
├─ Python 메인 스레드
│  ├─ IpcHandler 스레드              TCP server / Node와 JSON 송수신
│  ├─ 시장 크롤러 워커               환율·RSS·기사 HTML 수집
│  └─ 기사 분석 워커                 본문 키워드 필터 / Node 입력 JSON 생성
│
└─ Node.js 프로세스
   ├─ Node 메인 스레드               IPC 메시지 라우팅 / 워커 수명 관리
   ├─ IPC Worker 스레드              Python TCP 연결 / 줄 단위 JSON 처리
   └─ 인사이트 Worker 스레드         파일 입력 / 이동평균 분석 / 출력 파일 저장
```

이 명령은 `software_architecture/` 저장소 폴더의 상위 디렉터리에서 실행한다. 소스의 import는 `software_architecture.project.legacy` 패키지 경로를 사용한다.

이 구조에서 `threading.Thread`는 Python 내부 동시 실행 단위이고, Node의 `worker_threads.Worker`는 Node 프로세스 내부 작업 스레드다. Node.js 자체는 Python과 분리된 OS 프로세스다.

## 소스 파일별 안내

### `project/legacy/process_and_thread.py`: Python 실행 조립부

프로그램 실행 시작점이다.

1. 로깅을 설정하고 실행 파일 위치를 기준으로 파일 경로를 계산한다.
2. 크롤러 큐와 분석기 큐를 만든다.
3. Python IPC 서버 스레드를 시작해 사용 가능한 포트를 얻는다.
4. `node_process.js`를 별도 프로세스로 실행한다.
5. `CrawlerWorker`, `AnalyzerWorker`의 스레드를 시작한다.
6. 분석기에 `START`, 크롤러에 `START`를 넣는다.
7. 두 큐의 미완료 메시지가 모두 처리될 때까지 `Queue.join()`으로 기다린다.
8. 분석 입력 파일이 만들어졌는지 확인하고 Node에 파일 경로를 보낸다.
9. `INSIGHTS_SAVED` 응답을 기다린다.
10. Python 워커에 `STOP`, Node에 `STOP`을 보내고 종료를 기다린다.

**중요:** `Queue.join()`은 스레드가 끝날 때까지 기다리는 메서드가 아니다. 큐에 넣은 항목마다 워커가 `task_done()`을 호출할 때까지 기다린다. 실제 스레드 종료는 `thread.join()`이 기다린다.

### `project/legacy/thread_messages.py`: Python 내부 메시지 규격

`MessageType`은 워커 간 명령/이벤트 종류를 고정하고, `Message`는 타입·보낸 사람·payload를 담는 불변 데이터 객체다.

- `START`: 워커 작업 시작
- `DATA`: 수집된 환율·뉴스 payload 전달
- `DATA_PROCESSED`: 분석 입력 파일 생성 완료를 크롤러에 알림
- `STATUS_REQUEST` / `STATUS_RESPONSE`: 워커 상태 확인
- `STOP`: 정상 종료 요청
- `ERROR`: 실패 정보 전달

`Message`의 `start()`, `data()` 등 class method는 올바른 타입과 필드 순서로 메시지를 만드는 생성 편의 메서드다. 이 메시지들은 Python 프로세스 내부에서만 사용한다. Python-Node IPC는 별도의 JSON dict 프로토콜이다.

`FETCH`와 `Message.fetch()`도 정의되어 있지만 현재 환율·뉴스 파이프라인에서는 사용하지 않는 이전 예제의 잔여 프로토콜이다.

### `project/legacy/thread_worker.py`: Python 워커 로직

#### 데이터 요청 보조 함수

- `fetch_json(url)`: User-Agent와 5초 timeout으로 JSON API 요청
- `fetch_xml(url)`: RSS XML을 가져와 ElementTree로 파싱
- `fetch_article_body(url)`: RSS 항목 링크에서 HTML을 받아 텍스트 후보를 반환
- `ArticleTextParser`: script/style/nav 등 일부 요소를 제외하며 HTML 데이터 텍스트를 모음

`fetch_news()`는 RSS에서 제목·링크·발행일을 얻고 `ThreadPoolExecutor(max_workers=12)`로 기사 링크를 병렬 요청한다. 기사 요청이 실패하면 RSS의 description을 그대로 보존한다.

#### `CrawlerWorker`

큐에서 `START`를 받으면 환율과 뉴스를 수집한다.

- 환율 기간: 오늘 기준 과거 45일
- 기준 통화: USD
- 대상 통화: EUR, GBP, JPY, KRW, CNY, AUD, CAD, CHF
- 환율 서비스: Frankfurter API
- 뉴스 서비스: Google News RSS 검색

수집이 끝나면 `market_data_raw.json`을 쓰고 동일 payload를 `DATA` 메시지로 분석기 큐에 넣는다. 분석기 입력 저장 완료인 `DATA_PROCESSED`를 받으면 `WAITING` 상태가 된다.

상태는 작업의 진행 상황을 로그로 관찰하기 위한 값이다. 상태 enum 자체가 큐 소비를 차단하거나 전이를 검증하는 것은 아니다.

#### `AnalyzerWorker`

`DATA` payload에서 기사 제목과 본문을 소문자로 합쳐 정해 둔 키워드를 검색한다. 일치한 서로 다른 키워드가 2개 이상인 기사만 남긴다. 환율 시계열은 그대로 유지하고 기사에 `matched_keywords`를 덧붙여 `market_analysis_input.json`에 저장한다. 완료 후 크롤러 큐에 `DATA_PROCESSED`를 넣는다.

### `project/legacy/ipc_handler.py`: Python TCP IPC 어댑터

Python 메인 스레드와 소켓 처리 스레드 사이에서 두 개의 `queue.Queue`를 사용한다.

- `send(dict)`: Python 메인 스레드에서 나갈 메시지를 outbox에 넣음
- `inbox`: Node에서 받은 메시지를 메인 스레드가 꺼내는 큐
- `_run()`: localhost TCP 서버를 열고 Node 연결을 수락
- `_send_pending()`: outbox의 dict를 JSON으로 직렬화하고 뒤에 newline을 붙여 송신
- `_receive_messages()`: 바이트 청크를 버퍼에 붙인 뒤 newline이 있는 완성 메시지를 JSON으로 파싱

TCP는 메시지 경계를 제공하지 않는다. 한 번의 `recv()`가 JSON 한 개 전체를 반환한다는 보장이 없으므로 버퍼와 newline 구분자가 필요하다.

### `project/legacy/node_process.js`: Node 프로세스 및 두 Worker

같은 파일을 세 실행 문맥에서 사용한다.

- 메인 문맥(`isMainThread === true`): Worker 생성, 이벤트 라우팅, 프로세스 상태 관리
- `role: "ipc-handler"`: TCP socket 연결 및 JSON line 수신/송신
- `role: "insight-saver"`: 분석 입력을 읽고 인사이트 파일을 생성

#### `buildInsight(input)`

각 통화에 대해 숫자 환율만 모으고 마지막 5개 관측값의 산술 평균을 구한다. 휴일은 관측값이 없으므로 이름은 “5일”이지만 구현상 정확히는 **최근 5개 환율 관측치**다.

```text
차이율 = (최신 환율 - 최근 5개 관측치 평균) / 평균 × 100
```

- 차이율 `> 0.15%`: `상승 추이`
- 차이율 `< -0.15%`: `하락 추이`
- 나머지: 이동평균 부근 보합

`change_from_previous_day_percent`는 보조 정보다. 최종 `trend`는 이동평균 차이로 결정한다.

기사의 `headline`, `relevant_content`, `matched_reasons`를 출력 데이터로 만든다. `matched_reasons`는 본문에서 찾은 사전 키워드 목록이지, 환율 변화를 일으킨 원인을 입증한 결과는 아니다.

## 데이터 파일 역할

| 파일 | 생성 위치 | 역할 |
|---|---|---|
| `project/legacy/market_data_raw.json` | Python 크롤러 | 환율과 RSS/본문 수집 결과 원본 |
| `project/legacy/market_analysis_input.json` | Python 분석기 | 환율 + 관련 기사만 포함한 Node 입력 |
| `project/legacy/market_insights.json` | Node 인사이트 Worker | 이동평균 추이와 관련 기사 정보를 담은 최종 결과 |

IPC에는 위 데이터 전체가 아니라 `PROCESS_COMPLETE`와 입력/출력 경로만 전달한다.

## 메시지 및 완료 신호

### Python 내부

```text
Main -> Analyzer queue: START
Main -> Crawler queue: START
Crawler -> Analyzer queue: DATA
Analyzer -> Crawler queue: DATA_PROCESSED
Main: 각 큐의 join() 반환 확인
```

`DATA_PROCESSED`는 Node 저장 완료가 아니라 Python 분석 입력 파일 작성 완료 신호다. Node 저장 완료는 IPC의 `INSIGHTS_SAVED`다.

### Python-Node IPC

```text
Python -> Node: PROCESS_COMPLETE { analysisInputPath, outputPath }
Node -> Python: INSIGHTS_SAVED { outputPath, currencies }
Python -> Node: STOP
```

전송 형식은 UTF-8 JSON 한 줄 + `\n`이며, TCP 연결은 `127.0.0.1`의 임시 포트를 사용한다.

## 코드 읽는 순서

1. `project/legacy/process_and_thread.py`: 무엇을 만들고 어떤 순서로 기다리는지 본다.
2. `project/legacy/thread_messages.py`: Python 워커 메시지 계약을 본다.
3. `project/legacy/thread_worker.py`: 수집과 관련 기사 선택을 따라간다.
4. `project/legacy/ipc_handler.py`: 프로세스 경계에서 메시지가 어떻게 프레이밍되는지 본다.
5. `project/legacy/node_process.js`: IPC 라우팅과 인사이트 계산·저장을 본다.
6. `project/legacy/market_insights.json`: 계산 결과의 실제 필드를 확인한다.

## 현재 구현의 한계와 주의점

- **HTML 본문 추출은 일반적인 본문 파서가 아니다.** `ArticleTextParser.handle_data()`의 조건은 `in_content`가 false여도 공백이 아닌 텍스트를 추가하므로, skip 목록에 없는 페이지 전체 텍스트가 들어올 수 있다. `<article>` 또는 `<main>` 영역만 추출하려는 의도와 구현이 완전히 일치하지 않는다.
- **뉴스 페이지는 사이트마다 다르다.** 리다이렉트, 차단, 인코딩, 동적 렌더링 때문에 본문 요청이 실패할 수 있으며 이 경우 RSS description이 사용된다.
- **분석 결과는 투자 자문이 아니다.** 단순 이동평균 및 키워드 일치는 추세 요약과 기사 후보 선별이며, 인과관계를 증명하지 않는다.
- **`reason_summary`는 실제 빈도 계산이 아니다.** 현재 Node 코드는 관련 기사가 한 건 이상이면 고정 요약 문자열을 사용한다. 기사별 `matched_reasons`와 전체 요약의 집계는 구별해야 한다.
- **치명적 종료 경로의 정리가 제한적이다.** 정상 경로는 모든 워커를 정지시키지만, Python에서 `NODE_ERROR`를 받았을 때는 즉시 예외를 던져 실행 중인 Python 스레드나 Node 프로세스 정리가 생략될 수 있다.
- **큐와 네트워크 대기에는 timeout이 다르게 적용된다.** 외부 HTTP 요청은 5초 timeout이 있지만, Python 메인 스레드의 `ipc.inbox.get()`은 무기한 대기한다. Node가 응답하지 않으면 실행도 계속 기다린다.
- **상태 로거는 전이를 검증하지 않는다.** `transition()`은 현재 상태와 다음 상태를 출력하고 값을 반환할 뿐, 허용되지 않은 전이를 거부하지 않는다.

이 항목들은 현재 코드의 동작을 이해하기 위한 관찰 사항이다. 문서 작성과 주석 추가 범위에서는 동작을 임의로 변경하지 않았다.
