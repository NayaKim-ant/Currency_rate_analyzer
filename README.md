# 환율·뉴스 인사이트 분석기

Python과 Node.js로 구성된 학습용 멀티프로세스·멀티스레드 프로젝트다. Python은 환율과 뉴스 데이터를 수집하고 관련 기사를 선별한다. Node.js는 통화별 이동평균 추이와 기사 정보를 분석해 `market_insights.json`을 만든다.

## 시작하기

```powershell
python process_and_thread.py
```

Node.js가 필요하다. 실행기는 PATH에서 `node`를 찾고, 없으면 Windows 사용자 설치 경로 `%LOCALAPPDATA%\nodejs\node.exe`를 확인한다.

## 문서

- [코드베이스 분석 가이드](docs/codebase-guide.md): 파일별 책임, 호출 흐름, 메시지/큐, 상태, 알려진 한계
- [시스템 아키텍처](docs/architecture.md): 프로세스와 워커 구성
- [데이터 흐름](docs/data-flow.md): 수집부터 종료까지의 시퀀스
- [데이터 구조](docs/data-structure.md): Python 메시지, IPC JSON, 파일 스키마

## 주요 소스

| 파일 | 역할 |
|---|---|
| `process_and_thread.py` | Python 프로세스 실행 및 전체 생명주기 조립 |
| `thread_messages.py` | Python 워커 내부 메시지 타입 |
| `thread_worker.py` | 환율·뉴스 수집 및 기사 관련성 분석 |
| `ipc_handler.py` | Python TCP IPC 서버 스레드 |
| `node_process.js` | Node IPC Worker, 이동평균 분석, 인사이트 저장 |

실행 결과 파일은 이 디렉터리에 생성된다: `market_data_raw.json`, `market_analysis_input.json`, `market_insights.json`.
