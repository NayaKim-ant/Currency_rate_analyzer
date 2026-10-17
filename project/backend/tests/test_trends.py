from decimal import Decimal

import pytest

from app.services.trends import classify_trend, moving_average


def test_moving_average_uses_observations_and_leaves_short_windows_empty() -> None:
    rates = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4")]

    assert moving_average(rates, 3) == [None, None, Decimal("2"), Decimal("3")]


def test_moving_average_supports_one_observation_window() -> None:
    rates = [Decimal("1.25"), Decimal("1.75")]

    assert moving_average(rates, 1) == rates


def test_moving_average_rejects_non_positive_window() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        moving_average([Decimal("1")], 0)


@pytest.mark.parametrize(
    ("averages", "expected"),
    [
        ((Decimal("3"), Decimal("2"), Decimal("1")), "uptrend"),
        ((Decimal("1"), Decimal("2"), Decimal("3")), "downtrend"),
        ((Decimal("2"), Decimal("1"), Decimal("3")), "neutral"),
        ((Decimal("3"), None, Decimal("1")), "insufficient_data"),
    ],
)
def test_classify_trend(averages: tuple[Decimal | None, ...], expected: str) -> None:
    assert classify_trend(*averages) == expected
