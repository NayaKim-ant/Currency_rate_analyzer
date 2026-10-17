from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.services.trends import moving_average


@dataclass(frozen=True)
class MarketSignal:
    signal_type: str
    occurred_on: date
    observed_value: Decimal


def detect_price_signals(
    observations: Sequence[tuple[date, Decimal]],
    threshold_percent: Decimal = Decimal("2"),
) -> list[MarketSignal]:
    if threshold_percent <= 0:
        raise ValueError("threshold_percent must be greater than zero")

    signals: list[MarketSignal] = []
    for (previous_date, previous_rate), (current_date, current_rate) in zip(observations, observations[1:]):
        if previous_rate <= 0 or current_rate <= 0:
            raise ValueError("rates must be positive")
        change_percent = (current_rate - previous_rate) / previous_rate * Decimal("100")
        if change_percent >= threshold_percent:
            signals.append(MarketSignal("rapid_rise", current_date, change_percent))
            signals.append(MarketSignal("change_point_candidate", current_date, change_percent))
        elif change_percent <= -threshold_percent:
            signals.append(MarketSignal("rapid_fall", current_date, change_percent))
            signals.append(MarketSignal("change_point_candidate", current_date, change_percent))
    return signals


def detect_trend_reversals(
    observations: Sequence[tuple[date, Decimal]],
    short_window: int = 5,
    long_window: int = 20,
) -> list[MarketSignal]:
    if short_window <= 0 or long_window <= short_window:
        raise ValueError("windows must satisfy 0 < short_window < long_window")

    values = [rate for _, rate in observations]
    short_averages = moving_average(values, short_window)
    long_averages = moving_average(values, long_window)
    signals: list[MarketSignal] = []
    previous_difference: Decimal | None = None

    for index, (short_average, long_average) in enumerate(zip(short_averages, long_averages)):
        if short_average is None or long_average is None:
            continue
        difference = short_average - long_average
        if previous_difference is not None:
            if previous_difference < 0 <= difference:
                signals.append(MarketSignal("trend_reversal_up", observations[index][0], difference))
            elif previous_difference > 0 >= difference:
                signals.append(MarketSignal("trend_reversal_down", observations[index][0], difference))
        previous_difference = difference
    return signals


def link_policy_articles_to_changes(
    policy_publication_dates: Sequence[date],
    change_dates: Sequence[date],
    window_days: int = 2,
) -> list[tuple[date, date]]:
    if window_days < 0:
        raise ValueError("window_days cannot be negative")

    return [
        (published_on, changed_on)
        for published_on in policy_publication_dates
        for changed_on in change_dates
        if abs((changed_on - published_on).days) <= window_days
    ]
