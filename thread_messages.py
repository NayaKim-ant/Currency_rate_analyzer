from dataclasses import dataclass
from enum import Enum, auto
from typing import Any


"""Python 프로세스 내부 워커 간 메시지 프로토콜."""


class MessageType(Enum):
    """큐로 전달되는 명령과 이벤트의 종류."""

    START = auto()
    FETCH = auto()
    DATA = auto()
    DATA_PROCESSED = auto()
    STATUS_REQUEST = auto()
    STATUS_RESPONSE = auto()
    STOP = auto()
    ERROR = auto()


@dataclass(frozen=True, slots=True)
class Message:
    """불변 메시지 봉투; payload에 실제 데이터를 담는다."""

    message_type: MessageType
    sender: int | None = None
    payload: Any = None

    @classmethod
    def start(cls, sender: int | None = None) -> "Message":
        return cls(MessageType.START, sender)

    @classmethod
    def fetch(cls, sender: int) -> "Message":
        return cls(MessageType.FETCH, sender)

    @classmethod
    def data(cls, sender: int, payload: Any) -> "Message":
        return cls(MessageType.DATA, sender, payload)

    @classmethod
    def data_processed(cls, sender: int, payload: Any) -> "Message":
        return cls(MessageType.DATA_PROCESSED, sender, payload)

    @classmethod
    def status_request(cls, sender: int) -> "Message":
        return cls(MessageType.STATUS_REQUEST, sender)

    @classmethod
    def status_response(cls, sender: int, payload: Any) -> "Message":
        return cls(MessageType.STATUS_RESPONSE, sender, payload)

    @classmethod
    def stop(cls, sender: int | None = None) -> "Message":
        return cls(MessageType.STOP, sender)

    @classmethod
    def error(cls, sender: int, payload: str) -> "Message":
        return cls(MessageType.ERROR, sender, payload)
