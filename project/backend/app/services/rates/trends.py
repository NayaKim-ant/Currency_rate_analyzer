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


def build_rate_points(
    rows: Sequence[object],
    warmup_rows: Sequence[object],
    quote_direction: str = "target_per_base",
) -> tuple[list[dict], str]:
    from app.schemas.rates import RatePoint

    values = [row.rate for row in list(warmup_rows) + list(rows)]
    if quote_direction == "base_per_target":
        values = [Decimal("1") / value for value in values]
    averages = {window: moving_average(values, window) for window in (5, 20, 60)}
    warmup_len = len(warmup_rows)
    points = [
        RatePoint(
            rate_date=row.rate_date,
            rate=values[index + warmup_len],
            ma_5=averages[5][index + warmup_len],
            ma_20=averages[20][index + warmup_len],
            ma_60=averages[60][index + warmup_len],
        )
        for index, row in enumerate(rows)
    ]
    trend_state = "insufficient_data"
    if points:
        latest = points[-1]
        trend_state = classify_trend(latest.ma_5, latest.ma_20, latest.ma_60)
    return points, trend_state

