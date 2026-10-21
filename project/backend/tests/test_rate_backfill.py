from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.rates import ExchangeRate
from app.services.rates import collector as collection


def test_rate_sync_backfills_gaps_and_updates_existing_rows(test_database, monkeypatch) -> None:
    end_date = date.today()
    start_date = end_date - timedelta(days=2)
    records = [
        {
            "base_currency": "USD",
            "target_currency": "KRW",
            "rate_date": start_date + timedelta(days=offset),
            "rate": Decimal("1300") + Decimal(offset),
            "source": "frankfurter",
        }
        for offset in range(3)
    ]
    requested_ranges: list[tuple[date, date]] = []

    def fetch_range(start: date, end: date, base_currency: str = "USD"):
        requested_ranges.append((start, end))
        return records

    monkeypatch.setattr(collection, "fetch_rate_history", fetch_range)
    with Session(test_database) as session:
        session.add(
            ExchangeRate(
                base_currency="USD",
                target_currency="KRW",
                rate_date=start_date + timedelta(days=1),
                rate=Decimal("1"),
                source="old",
            )
        )
        session.commit()

        assert collection.collect_recent_rates(session, days=3) == 3
        assert collection.collect_recent_rates(session, days=3) == 3
        stored_rates = list(
            session.scalars(
                select(ExchangeRate).order_by(ExchangeRate.rate_date)
            )
        )

    assert requested_ranges == [(start_date, end_date), (start_date, end_date)]
    assert len(stored_rates) == 3
    assert stored_rates[1].rate == Decimal("1301")
    assert stored_rates[1].source == "frankfurter"
