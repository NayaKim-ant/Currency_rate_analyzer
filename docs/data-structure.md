# 데이터 구조와 메시지 계약

> 이 문서는 `project/legacy/` 프로토타입의 Python 메시지, TCP IPC, JSON 파일 계약을 설명한다. 현재 backend는 API 스키마와 PostgreSQL 모델을 사용한다. 전환 완료 및 계약 검증 결과는 [검증 보고서](verification.md)를 참고한다.

## Python 내부 메시지

`thread_messages.py`의 `Message`는 Python 워커 사이에서 사용하는 불변 데이터 객체다.

```python
@dataclass(frozen=True, slots=True)
class Message:
    message_type: MessageType
    sender: int | None = None
    payload: Any = None
```

### 메시지 타입

| 타입 | 방향 | 의미 |
|---|---|---|
| `START` | 실행기 -> 워커 | 워커 작업 시작 |
| `DATA` | 크롤러 -> 분석기 | 수집 데이터 전달 |
| `DATA_PROCESSED` | 분석기 -> 크롤러 | 관련성 분석 및 입력 저장 완료 |
| `STATUS_REQUEST` | 워커 간 | 상대 상태 요청 |
| `STATUS_RESPONSE` | 워커 간 | 상태 응답 |
| `STOP` | 실행기 -> 워커 | 정상 종료 |
| `ERROR` | 워커 간 | 오류 전달 |

## Python 원본 데이터

파일: `market_data_raw.json`

```json
{
  "collected_at": "2026-09-19",
  "rates": [
    {
      "date": "2026-09-18",
      "base": "USD",
      "rates": {
        "EUR": 0.8726,
        "JPY": 157.89,
        "KRW": 1388.1
      }
    }
  ],
  "articles": [
    {
      "title": "기사 제목",
      "description": "기사 설명",
      "link": "https://example.com/article",
      "published": "시간"
    }
  ]
}
```

## Node 입력 데이터

파일: `market_analysis_input.json`

원본 구조를 유지하면서 Python이 관련 기사만 남긴다.

```json
{
  "collected_at": "2026-09-19",
  "rates": "환율 시계열 배열",
  "articles": [
    {
      "title": "기사 제목",
      "description": "기사 설명",
      "link": "기사 링크",
      "published": "발행 시각",
      "matched_keywords": ["rate", "dollar"]
    }
  ],
  "currency_names": {
    "EUR": "유로",
    "JPY": "일본 엔",
    "KRW": "한국 원"
  }
}
```

## Node IPC 메시지

Python과 Node는 localhost TCP를 사용하며, 메시지 하나를 JSON 한 줄로 표현한다.

### Python -> Node

```json
{
  "type": "PROCESS_COMPLETE",
  "analysisInputPath": "market_analysis_input.json",
  "outputPath": "market_insights.json"
}
```

종료 메시지:

```json
{
  "type": "STOP"
}
```

### Node -> Python

저장 완료:

```json
{
  "type": "INSIGHTS_SAVED",
  "outputPath": "market_insights.json",
  "currencies": 8
}
```

오류:

```json
{
  "type": "NODE_ERROR",
  "error": "오류 설명"
}
```

## 최종 인사이트 구조

파일: `market_insights.json`

```json
{
  "generated_at": "2026-09-19T09:38:35.168Z",
  "source_period": {
    "start": "2026-08-05",
    "end": "2026-09-18"
  },
  "methodology": "5일 단순 이동평균과 최신 환율을 비교해 일시적 등락보다 추이를 판단",
  "currencies": {
    "EUR": {
      "name": "유로",
      "latest_rate": 0.8726,
      "latest_date": "2026-09-18",
      "five_day_moving_average": 0.868548,
      "change_from_previous_day_percent": 0.184,
      "gap_from_moving_average_percent": 0.467,
      "trend": "상승 추이"
    }
  },
  "relevant_articles": [
    {
      "headline": "기사 제목",
      "relevant_content": "관련 내용",
      "published": "발행 시각",
      "link": "기사 링크",
      "matched_reasons": ["rate", "dollar"],
      "matched_keywords": ["rate", "dollar"]
    }
  ],
  "reason_summary": "기사에서 반복된 변화 이유 후보 요약"
}
```

## 이동평균 계산

통화별 환율 배열을 $x_1, x_2, \dots, x_n$이라고 할 때 최근 5일 이동평균은 다음과 같다.

$$
MA_5 = \frac{x_{n-4} + x_{n-3} + x_{n-2} + x_{n-1} + x_n}{5}
$$

최신값과 이동평균의 차이는 다음 기준으로 해석한다.

- 최신값이 이동평균보다 `0.15%` 초과 높음: `상승 추이`
- 최신값이 이동평균보다 `0.15%` 초과 낮음: `하락 추이`
- 그 사이: `이동평균 부근의 보합 추이`

전일 대비 변화율은 보조 지표일 뿐이며, 최종 추이는 이동평균과의 위치를 우선한다.
