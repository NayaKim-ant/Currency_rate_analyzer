# Project Layout

`project/`에는 실행 가능한 애플리케이션과 기존 프로토타입을 둔다. 저장소 루트의 `docs/`에는 이 구조와 동작을 설명하는 문서를 둔다.

```text
project/
  backend/   Python + FastAPI + PostgreSQL 서비스
  frontend/  Next.js 웹 애플리케이션
  legacy/    기존 Python/Node.js 프로토타입과 JSON 산출물
```

## 현재 상태

- `backend/`와 `frontend/`는 새 구현을 위한 폴더 골격이다. 앱 진입점과 의존성은 아직 구성하지 않았다.
- `legacy/`는 기존 실행을 보존한다. `software_architecture/` 저장소 폴더의 상위 디렉터리에서 `python -m software_architecture.project.legacy.process_and_thread`로 실행한다.
- 기존 프로토타입의 상대 경로 출력은 `project/legacy/`에 유지된다.
- 새 기능은 `backend/` 또는 `frontend/`에 구현하고, `legacy/`는 비교·참고용으로만 둔다.

각 하위 폴더의 상세 책임은 해당 디렉터리의 README를 참고한다.
