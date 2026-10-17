import json
import queue
import socket
import threading
from typing import Any


class IpcHandler:
    """Python 메인 스레드와 Node 프로세스 사이의 TCP/JSON 어댑터.

    소켓 I/O는 전용 스레드가 맡고, 호출자는 thread-safe Queue로 메시지를
    송수신해 메인 스레드가 네트워크 읽기에서 막히지 않도록 한다.
    """

    def __init__(self, host: str = "127.0.0.1") -> None:
        self.host = host
        self.port = 0
        self._server_socket: socket.socket | None = None
        self._client_socket: socket.socket | None = None
        self._outbox: queue.Queue[dict[str, Any]] = queue.Queue()
        self._inbox: queue.Queue[dict[str, Any]] = queue.Queue()
        self._connected = threading.Event()
        self._ready = threading.Event()
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._run, name="python-ipc-handler")

    @property
    def inbox(self) -> queue.Queue[dict[str, Any]]:
        return self._inbox

    def start(self) -> None:
        """서버 소켓을 열고 임시 포트 준비가 끝날 때까지 기다린다."""
        self._thread.start()
        self._ready.wait()

    def send(self, message: dict[str, Any]) -> None:
        self._outbox.put(message)

    def stop(self) -> None:
        self._stopped.set()
        self._outbox.put({"type": "STOP"})
        if self._thread.is_alive():
            self._thread.join(timeout=3)

    def _run(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            self._server_socket = server_socket
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((self.host, 0))
            self.port = server_socket.getsockname()[1]
            server_socket.listen(1)
            server_socket.settimeout(0.5)
            self._ready.set()

            while not self._stopped.is_set():
                try:
                    client_socket, _ = server_socket.accept()
                    break
                except socket.timeout:
                    continue
            else:
                return

            with client_socket:
                self._client_socket = client_socket
                self._connected.set()
                client_socket.settimeout(0.2)
                buffer = b""
                while not self._stopped.is_set():
                    # 발신 큐를 비운 뒤 수신한다. recv timeout은 stop 플래그를
                    # 주기적으로 확인할 기회를 제공하며 polling loop와는 다르다.
                    self._send_pending(client_socket)
                    try:
                        chunk = client_socket.recv(4096)
                    except socket.timeout:
                        continue
                    if not chunk:
                        break
                    buffer += chunk
                    buffer = self._receive_messages(buffer)

    def _send_pending(self, client_socket: socket.socket) -> None:
        """큐의 각 dict를 JSON 한 줄로 직렬화해 TCP 소켓에 쓴다."""
        while True:
            try:
                message = self._outbox.get_nowait()
            except queue.Empty:
                return
            payload = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
            client_socket.sendall(payload)
            self._outbox.task_done()

    def _receive_messages(self, buffer: bytes) -> bytes:
        """TCP 청크 경계를 넘어온 데이터를 newline 단위 메시지로 복원한다."""
        while b"\n" in buffer:
            raw_message, buffer = buffer.split(b"\n", 1)
            if raw_message:
                self._inbox.put(json.loads(raw_message.decode("utf-8")))
        return buffer
