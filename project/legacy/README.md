# Legacy Prototype

기존 Python·Node.js·로컬 큐·TCP IPC·JSON 파일 기반 프로토타입이다. 새 FastAPI/PostgreSQL backend와 Next.js frontend로 옮기는 동안 동작 비교 및 기존 코드 참고용으로 보존한다.

`software_architecture/` 저장소 폴더의 상위 디렉터리에서 실행:

```powershell
python -m software_architecture.project.legacy.process_and_thread
```

입출력 JSON은 이 디렉터리에 생성된다. 이 프로토타입은 새 backend/frontend 구조와 별도로 유지하며, 새 기능은 여기에 추가하지 않는다.
