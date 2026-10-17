from datetime import date
from decimal import Decimal

import pytest

from app.services.collection import parse_rate_history


def test_parse_rate_history_normalizes_and_sorts_records() -> None:
    payload = {
        "rates": {
            "2026-10-14": {"KRW": 1420.25, "USD": 1},
            "2026-10-12": {"KRW": 1418.5},
        }
    }

    records = parse_rate_history(payload, "usd", ["krw"])

    assert [record["rate_date"] for record in records] == [date(2026, 10, 12), date(2026, 10, 14)]
    assert [record["rate"] for record in records] == [Decimal("1418.5"), Decimal("1420.25")]
    assert all(record["base_currency"] == "USD" for record in records)
    assert all(record["target_currency"] == "KRW" for record in records)


def test_parse_rate_history_rejects_invalid_or_non_positive_rates() -> None:
    with pytest.raises(ValueError, match="must be positive and finite"):
        parse_rate_history({"rates": {"2026-10-14": {"KRW": 0}}}, "USD", ["KRW"])
