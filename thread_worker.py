import json
import logging
import queue
from datetime import date, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ElementTree

from thread_messages import Message, MessageType

logger = logging.getLogger(__name__)


class CrawlerState(Enum):
    IDLE = auto()
    FETCHING_RATES = auto()
    FETCHING_NEWS = auto()
    SENT = auto()
    WAITING = auto()
    STOPPED = auto()
    ERROR = auto()


class AnalyzerState(Enum):
    IDLE = auto()
    RECEIVING = auto()
    FILTERING = auto()
    SAVING = auto()
    WAITING = auto()
    STOPPED = auto()
    ERROR = auto()


MAJOR_CURRENCIES = {
    "EUR": "유로",
    "GBP": "영국 파운드",
    "JPY": "일본 엔",
    "KRW": "한국 원",
    "CNY": "중국 위안",
    "AUD": "호주 달러",
    "CAD": "캐나다 달러",
    "CHF": "스위스 프랑",
}


def fetch_json(url: str) -> Any:
    request = Request(url, headers={"User-Agent": "market-insight-example/1.0"})
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def fetch_xml(url: str) -> ElementTree.Element:
    request = Request(url, headers={"User-Agent": "market-insight-example/1.0"})
    with urlopen(request, timeout=15) as response:
        return ElementTree.fromstring(response.read())


class CrawlerWorker:
    def __init__(self, inbox: queue.Queue[Message], analyzer_inbox: queue.Queue[Message], raw_output_path: Path) -> None:
        self.inbox = inbox
        self.analyzer_inbox = analyzer_inbox
        self.raw_output_path = raw_output_path
        self.state = CrawlerState.IDLE

    def transition_to(self, new_state: CrawlerState, event: MessageType, detail: str = "") -> None:
        old_state = self.state
        self.state = new_state
        logger.info("시장 크롤러 상태 전이: %s -> %s | 원인 이벤트: %s%s", old_state.name, new_state.name, event.name, f" | {detail}" if detail else "")

    def run(self) -> None:
        while self.state is not CrawlerState.STOPPED:
            message = self.inbox.get()
            try:
                self.handle(message)
            finally:
                self.inbox.task_done()

    def handle(self, message: Message) -> None:
        if message.message_type is MessageType.START:
            self.collect_market_data()
        elif message.message_type is MessageType.STATUS_REQUEST:
            self.analyzer_inbox.put(Message.status_response(1, {"worker": "market-crawler", "state": self.state.name}))
        elif message.message_type is MessageType.DATA_PROCESSED:
            self.transition_to(CrawlerState.WAITING, MessageType.DATA_PROCESSED, "Node 인사이트 저장 완료")
        elif message.message_type is MessageType.STOP:
            self.transition_to(CrawlerState.STOPPED, MessageType.STOP)
        elif message.message_type is MessageType.ERROR:
            self.transition_to(CrawlerState.ERROR, MessageType.ERROR, str(message.payload))

    def collect_market_data(self) -> None:
        try:
            rates = self.fetch_rates()
            self.transition_to(CrawlerState.FETCHING_NEWS, MessageType.DATA, "환율 시계열 수집 완료")
            articles = self.fetch_news()
            payload = {"rates": rates, "articles": articles, "collected_at": date.today().isoformat()}
            self.raw_output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self.transition_to(CrawlerState.SENT, MessageType.DATA, f"환율 {len(rates)}일, 기사 {len(articles)}개 수집")
            self.analyzer_inbox.put(Message.data(1, payload))
        except Exception as error:
            self.transition_to(CrawlerState.ERROR, MessageType.ERROR, str(error))
            self.analyzer_inbox.put(Message.error(1, str(error)))
            logger.exception("시장 데이터 수집 실패")

    def fetch_rates(self) -> list[dict[str, Any]]:
        self.transition_to(CrawlerState.FETCHING_RATES, MessageType.START, "주요 통화 환율 수집")
        end = date.today()
        start = end - timedelta(days=45)
        currencies = ",".join(MAJOR_CURRENCIES)
        url = f"https://api.frankfurter.app/{start.isoformat()}..{end.isoformat()}?from=USD&to={currencies}"
        response = fetch_json(url)
        return [{"date": rate_date, "base": "USD", "rates": values} for rate_date, values in sorted(response.get("rates", {}).items())]

    def fetch_news(self) -> list[dict[str, str]]:
        terms = "exchange rate dollar euro pound yen yuan won central bank inflation interest rate"
        url = f"https://news.google.com/rss/search?q={quote(terms)}&hl=en-US&gl=US&ceid=US:en"
        root = fetch_xml(url)
        articles = []
        for item in root.findall("./channel/item"):
            title = item.findtext("title", default="").strip()
            if title:
                articles.append({"title": title, "description": item.findtext("description", default="").strip(), "link": item.findtext("link", default="").strip(), "published": item.findtext("pubDate", default="").strip()})
        return articles[:100]


class AnalyzerWorker:
    def __init__(self, inbox: queue.Queue[Message], crawler_inbox: queue.Queue[Message], input_path: Path) -> None:
        self.inbox = inbox
        self.crawler_inbox = crawler_inbox
        self.input_path = input_path
        self.state = AnalyzerState.IDLE

    def transition_to(self, new_state: AnalyzerState, event: MessageType, detail: str = "") -> None:
        old_state = self.state
        self.state = new_state
        logger.info("기사 분석기 상태 전이: %s -> %s | 원인 이벤트: %s%s", old_state.name, new_state.name, event.name, f" | {detail}" if detail else "")

    def run(self) -> None:
        while self.state is not AnalyzerState.STOPPED:
            message = self.inbox.get()
            try:
                self.handle(message)
            finally:
                self.inbox.task_done()

    def handle(self, message: Message) -> None:
        if message.message_type is MessageType.START:
            self.transition_to(AnalyzerState.RECEIVING, MessageType.START)
        elif message.message_type is MessageType.DATA:
            self.transition_to(AnalyzerState.FILTERING, MessageType.DATA, "환율과 관련된 기사 선별")
            self.save_input(message.payload)
        elif message.message_type is MessageType.STATUS_REQUEST:
            self.crawler_inbox.put(Message.status_response(2, {"worker": "article-analyzer", "state": self.state.name}))
        elif message.message_type is MessageType.STOP:
            self.transition_to(AnalyzerState.STOPPED, MessageType.STOP)
        elif message.message_type is MessageType.ERROR:
            self.transition_to(AnalyzerState.ERROR, MessageType.ERROR, str(message.payload))

    def save_input(self, payload: dict[str, Any]) -> None:
        keywords = set("exchange rate dollar euro pound yen yuan won central bank inflation interest currency".split())
        relevant_articles = []
        for article in payload["articles"]:
            text = f'{article["title"]} {article["description"]}'.lower()
            matched = sorted({keyword for keyword in keywords if keyword in text})
            if len(matched) >= 2:
                relevant_articles.append({**article, "matched_keywords": matched})
        prepared = {"collected_at": payload["collected_at"], "rates": payload["rates"], "articles": relevant_articles, "currency_names": MAJOR_CURRENCIES}
        self.transition_to(AnalyzerState.SAVING, MessageType.DATA, f"관련 기사 {len(relevant_articles)}개 저장")
        self.input_path.write_text(json.dumps(prepared, ensure_ascii=False, indent=2), encoding="utf-8")
        self.transition_to(AnalyzerState.WAITING, MessageType.DATA, f"Node 입력 파일 생성: {self.input_path.name}")
        self.crawler_inbox.put(Message.data_processed(2, {"relevant_articles": len(relevant_articles)}))
        logger.info("Node 분석 입력 저장 완료: %s", self.input_path)
