from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.services.signals import detect_price_signals, detect_trend_reversals, link_policy_articles_to_changes


def test_detect_price_signals_flags_rise_and_fall_with_percentage_evidence() -> None:
    start = date(2026, 10, 1)
    observations = [
        (start, Decimal("100")),
        (start + timedelta(days=1), Decimal("103")),
        (start + timedelta(days=2), Decimal("100")),
    ]

    signals = detect_price_signals(observations, Decimal("2"))

    assert [signal.signal_type for signal in signals] == [
        "rapid_rise",
        "change_point_candidate",
        "rapid_fall",
        "change_point_candidate",
    ]
    assert signals[0].observed_value == Decimal("3")
    assert signals[2].observed_value < 0


def test_detect_trend_reversals_reports_moving_average_cross() -> None:
    start = date(2026, 10, 1)
    rates = [Decimal(value) for value in ("1", "2", "3", "2", "1")]
    observations = [(start + timedelta(days=index), rate) for index, rate in enumerate(rates)]

    signals = detect_trend_reversals(observations, short_window=2, long_window=3)

    assert len(signals) == 1
    assert signals[0].signal_type == "trend_reversal_down"
    assert signals[0].occurred_on == start + timedelta(days=4)


def test_policy_article_link_is_temporal_candidate_not_causation() -> None:
    article_day = date(2026, 10, 10)
    change_day = date(2026, 10, 12)

    assert link_policy_articles_to_changes([article_day], [change_day], window_days=2) == [
        (article_day, change_day)
    ]
    assert link_policy_articles_to_changes([article_day], [change_day], window_days=1) == []


def test_signal_threshold_must_be_positive() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        detect_price_signals([], Decimal("0"))
