import logging
import os
import queue
import shutil
import subprocess
import threading
from pathlib import Path

from software_architecture.project.legacy.ipc_handler import IpcHandler
from software_architecture.project.legacy.thread_messages import Message
from software_architecture.project.legacy.thread_worker import AnalyzerWorker, CrawlerWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

# 모든 출력 파일을 실행 스크립트 위치에 두어 현재 작업 디렉터리에 좌우되지 않게 한다.
base_path = Path(__file__).parent
crawler_inbox: queue.Queue[Message] = queue.Queue()
analyzer_inbox: queue.Queue[Message] = queue.Queue()
raw_market_path = base_path / "market_data_raw.json"
analysis_input_path = base_path / "market_analysis_input.json"
insights_path = base_path / "market_insights.json"

ipc = IpcHandler()
ipc.start()
# Node 경로가 PATH에 없더라도 이전 사용자 영역 설치를 찾도록 fallback을 둔다.
node_executable = shutil.which("node") or str(Path(os.environ["LOCALAPPDATA"]) / "nodejs" / "node.exe")
try:
    node_process = subprocess.Popen(
        [node_executable, str(base_path / "node_process.js"), str(ipc.port)],
        cwd=base_path,
    )
except FileNotFoundError as error:
    ipc.stop()
    raise RuntimeError("Node.js가 필요합니다. Node.js 설치 후 다시 실행하세요.") from error

crawler = CrawlerWorker(crawler_inbox, analyzer_inbox, raw_market_path)
analyzer = AnalyzerWorker(analyzer_inbox, crawler_inbox, analysis_input_path)
threads = [
    threading.Thread(target=crawler.run, name="market-crawler-worker"),
    threading.Thread(target=analyzer.run, name="article-analyzer-worker"),
]

for thread in threads:
    thread.start()

# 분석기가 먼저 준비되어야 크롤러가 보낸 DATA를 놓치지 않는다.
analyzer_inbox.put(Message.start(0))
crawler_inbox.put(Message.start(0))

# Queue.join은 스레드 종료가 아니라 put된 항목마다 task_done이 호출될 때까지 기다린다.
crawler_inbox.join()
analyzer_inbox.join()

if not analysis_input_path.exists():
    crawler_inbox.put(Message.stop(0))
    analyzer_inbox.put(Message.stop(0))
    for thread in threads:
        thread.join(timeout=2)
    ipc.stop()
    node_process.terminate()
    raise RuntimeError("환율·뉴스 수집 또는 기사 분석에 실패해 Node 입력 파일이 생성되지 않았습니다.")

# 큰 환율·기사 payload는 이미 파일에 있으므로 IPC에는 경로만 보낸다.
ipc.send({
    "type": "PROCESS_COMPLETE",
    "analysisInputPath": str(analysis_input_path),
    "outputPath": str(insights_path),
})

while True:
    message = ipc.inbox.get()
    if message.get("type") == "INSIGHTS_SAVED":
        logging.info("Python IPC: Node 인사이트 저장 완료 - %s", message.get("outputPath"))
        break
    if message.get("type") == "NODE_ERROR":
        raise RuntimeError(message.get("error"))

# 저장 확인 뒤 Python 워커와 Node 프로세스를 명시적으로 종료한다.
crawler_inbox.put(Message.status_request(2))
analyzer_inbox.put(Message.status_request(1))
crawler_inbox.join()
analyzer_inbox.join()

crawler_inbox.put(Message.stop(0))
analyzer_inbox.put(Message.stop(0))
for thread in threads:
    thread.join()

ipc.send({"type": "STOP"})
node_process.wait(timeout=5)
ipc.stop()

print(f"시장 데이터 원본: {raw_market_path}")
print(f"인사이트 결과: {insights_path}")
