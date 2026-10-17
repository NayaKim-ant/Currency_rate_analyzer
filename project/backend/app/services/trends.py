from collections.abc import Sequence
from decimal import Decimal


def moving_average(values: Sequence[Decimal], window: int) -> list[Decimal | None]:
    if window <= 0:
        raise ValueError("window must be greater than zero")

    averages: list[Decimal | None] = []
    for index in range(len(values)):
        if index + 1 < window:
            averages.append(None)
            continue
        sample = values[index - window + 1 : index + 1]
        averages.append(sum(sample, start=Decimal("0")) / window)
    return averages


def classify_trend(
    ma_5: Decimal | None,
    ma_20: Decimal | None,
    ma_60: Decimal | None,
) -> str:
    if ma_5 is None or ma_20 is None or ma_60 is None:
        return "insufficient_data"
    if ma_5 > ma_20 > ma_60:
        return "uptrend"
    if ma_5 < ma_20 < ma_60:
        return "downtrend"
    return "neutral"
