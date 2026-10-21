from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models.rates import ExchangeRate

client = TestClient(app)


def test_health_endpoint_reports_api_liveness() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_rate_series_endpoint_is_in_openapi_contract() -> None:
    assert "/api/v1/rates" in app.openapi()["paths"]


def test_rate_series_endpoint_returns_moving_averages_and_trend(test_database) -> None:
    start_date = date.today() - timedelta(days=59)
    with Session(test_database) as session:
        session.add_all(
            [
                ExchangeRate(
                    base_currency="USD",
                    target_currency="KRW",
                    rate_date=start_date + timedelta(days=index),
                    rate=Decimal("1") + Decimal(index) / Decimal("100"),
                    source="test",
                )
                for index in range(60)
            ]
        )
        session.commit()

    response = client.get("/api/v1/rates?base_currency=USD&target_currency=krw&days=90")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["points"]) == 60
    assert payload["points"][3]["ma_5"] is None
    assert Decimal(str(payload["points"][4]["ma_5"])) == Decimal("1.02")
    assert payload["trend_state"] == "uptrend"


def test_changing_display_window_does_not_change_latest_averages(test_database):
    with Session(test_database) as session:
        session.add_all([
            ExchangeRate(base_currency="USD", target_currency="KRW", rate_date=date.today() - timedelta(days=79-i),
                         rate=Decimal(i + 1), source="test")
            for i in range(80)
        ])
        session.commit()
    short = client.get("/api/v1/rates?base_currency=USD&target_currency=KRW&days=30").json()
    long = client.get("/api/v1/rates?base_currency=USD&target_currency=KRW&days=90").json()
    assert len(short["points"]) == 30
    assert short["points"][-1] == long["points"][-1]
    assert short["trend_state"] == long["trend_state"] == "uptrend"
    assert Decimal(str(short["points"][0]["ma_20"])) == Decimal("41.5")
