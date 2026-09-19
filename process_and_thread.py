import logging
import os
import queue
import shutil
import subprocess
import threading
from pathlib import Path

from ipc_handler import IpcHandler
from thread_messages import Message
from thread_worker import AnalyzerWorker, CrawlerWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

base_path = Path(__file__).parent
crawler_inbox: queue.Queue[Message] = queue.Queue()
analyzer_inbox: queue.Queue[Message] = queue.Queue()
raw_market_path = base_path / "market_data_raw.json"
analysis_input_path = base_path / "market_analysis_input.json"
insights_path = base_path / "market_insights.json"

ipc = IpcHandler()
ipc.start()
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

analyzer_inbox.put(Message.start(0))
crawler_inbox.put(Message.start(0))

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
