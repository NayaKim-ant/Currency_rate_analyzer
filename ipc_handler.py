import json
import queue
import socket
import threading
from typing import Any


class IpcHandler:
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
        while True:
            try:
                message = self._outbox.get_nowait()
            except queue.Empty:
                return
            payload = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
            client_socket.sendall(payload)
            self._outbox.task_done()

    def _receive_messages(self, buffer: bytes) -> bytes:
        while b"\n" in buffer:
            raw_message, buffer = buffer.split(b"\n", 1)
            if raw_message:
                self._inbox.put(json.loads(raw_message.decode("utf-8")))
        return buffer
