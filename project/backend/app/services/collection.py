from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.currencies import FOREIGN_CURRENCIES, HOME_CURRENCY, SUPPORTED_CURRENCIES
from app.models.market import ExchangeRate

FRANKFURTER_URL = "https://api.frankfurter.dev/v1"
MAJOR_CURRENCIES = FOREIGN_CURRENCIES


def parse_rate_history(
    payload: Mapping[str, Any],
    base_currency: str,
    target_currencies: Sequence[str],
) -> list[dict[str, Any]]:
    raw_rates = payload.get("rates")
    if not isinstance(raw_rates, Mapping):
        raise ValueError("rate response must include a rates object")

    normalized_base = base_currency.upper()
    normalized_targets = {currency.upper() for currency in target_currencies}
    records: list[dict[str, Any]] = []
    for raw_date, raw_values in sorted(raw_rates.items()):
        if not isinstance(raw_values, Mapping):
            raise ValueError(f"rates for {raw_date} must be an object")
        try:
            rate_date = date.fromisoformat(str(raw_date))
        except ValueError as error:
            raise ValueError(f"invalid rate date: {raw_date}") from error

        for raw_currency, raw_rate in raw_values.items():
            currency = str(raw_currency).upper()
            if currency not in normalized_targets:
                continue
            try:
                rate = Decimal(str(raw_rate))
            except InvalidOperation as error:
                raise ValueError(f"invalid rate for {currency} on {rate_date}") from error
            if not rate.is_finite() or rate <= 0:
                raise ValueError(f"rate for {currency} on {rate_date} must be positive and finite")
            records.append({
                "base_currency": normalized_base,
                "target_currency": currency,
                "rate_date": rate_date,
                "rate": rate,
                "source": "frankfurter",
            })
    return records


def fetch_rate_history(
    start_date: date,
    end_date: date,
    base_currency: str = HOME_CURRENCY,
    target_currencies: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    if target_currencies is None:
        target_currencies = tuple(currency for currency in SUPPORTED_CURRENCIES if currency != base_currency.upper())
    normalized_base = base_currency.upper()
    # KRW-base provider quotes are rounded to too few decimal places for small
    # values such as USD per won. Derive them from the more precise USD quotes.
    source_base = "USD" if normalized_base == HOME_CURRENCY else normalized_base
    source_targets = tuple(dict.fromkeys(
        currency for currency in (*target_currencies, HOME_CURRENCY)
        if currency != source_base
    )) if normalized_base == HOME_CURRENCY else target_currencies
    response = httpx.get(
        f"{FRANKFURTER_URL}/{start_date.isoformat()}..{end_date.isoformat()}",
        params={"from": source_base, "to": ",".join(source_targets)},
        timeout=20.0,
    )
    response.raise_for_status()
    payload = response.json()
    if normalized_base == HOME_CURRENCY:
        source_rows = parse_rate_history(payload, source_base, source_targets)
        by_date: dict[date, dict[str, Decimal]] = {}
        for row in source_rows:
            by_date.setdefault(row["rate_date"], {"USD": Decimal("1")})[row["target_currency"]] = row["rate"]
        records = []
        for rate_date, values in sorted(by_date.items()):
            won_per_dollar = values.get(HOME_CURRENCY)
            if won_per_dollar is None:
                raise ValueError(f"KRW conversion rate missing on {rate_date}")
            for currency in target_currencies:
                if currency == HOME_CURRENCY or currency not in values:
                    continue
                records.append({
                    "base_currency": HOME_CURRENCY, "target_currency": currency, "rate_date": rate_date,
                    "rate": values[currency] / won_per_dollar, "source": "frankfurter-cross",
                })
        return records
    return parse_rate_history(payload, base_currency, target_currencies)


def store_rate_history(session: Session, records: Sequence[Mapping[str, Any]]) -> int:
    if not records:
        return 0

    statement = insert(ExchangeRate).values(list(records))
    statement = statement.on_conflict_do_update(
        constraint="uq_exchange_rates_pair_date",
        set_={"rate": statement.excluded.rate, "source": statement.excluded.source},
    )
    session.execute(statement)
    session.commit()
    return len(records)


def collect_recent_rates(session: Session, days: int = 365, base_currency: str = HOME_CURRENCY) -> int:
    if days < 1:
        raise ValueError("days must be at least one")
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)
    records = fetch_rate_history(start_date, end_date, base_currency)
    return store_rate_history(session, records)
