def test_alert_rule_can_be_created_and_listed(client, test_database) -> None:
    response = client.post(
        "/api/v1/alerts/rules",
        json={
            "base_currency": "usd",
            "target_currency": "krw",
            "alert_type": "rapid_rise",
            "threshold": "2.0",
            "lookback_days": 1,
        },
    )

    assert response.status_code == 201
    assert response.json()["target_currency"] == "KRW"
    assert response.json()["enabled"] is True
    assert client.get("/api/v1/alerts/rules").json()[0]["alert_type"] == "rapid_rise"


def test_alert_rule_rejects_non_positive_threshold(client, test_database) -> None:
    response = client.post(
        "/api/v1/alerts/rules",
        json={"target_currency": "KRW", "alert_type": "rapid_fall", "threshold": "0"},
    )

    assert response.status_code == 422
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.market import AlertEvent, ExchangeRate




@pytest.mark.parametrize("condition,threshold,expected", [
    ("won_cost_at_or_below", "1300", 1),
    ("won_cost_at_or_below", "1250", 1),
    ("won_cost_at_or_below", "1200", 0),
    ("won_cost_at_or_above", "1200", 1),
    ("won_cost_at_or_above", "1250", 1),
    ("won_cost_at_or_above", "1300", 0),
])
def test_won_price_alert_checks_latest_quote_on_creation_and_does_not_duplicate(
    client, test_database, condition, threshold, expected,
):
    with Session(test_database) as session:
        session.add(ExchangeRate(base_currency="KRW", target_currency="USD", rate_date=date.today(),
                                 rate=Decimal("0.0008"), source="test"))
        session.commit()
    response = client.post("/api/v1/alerts/rules", json={
        "target_currency": "USD", "alert_type": condition, "threshold": threshold,
    })
    assert response.status_code == 201
    occurrences = client.get("/api/v1/alerts?target_currency=USD").json()
    assert len(occurrences) == expected
    if expected:
        assert Decimal(str(occurrences[0]["measured_value"])) == Decimal("1250")
        assert "1 USD costs KRW 1,250" in occurrences[0]["message"]
    assert client.post("/api/v1/alerts/evaluate").json() == {"created": 0}
    assert len(client.get("/api/v1/alerts?target_currency=USD").json()) == expected


def test_price_rule_pause_resume_and_delete_preserve_notification_history(client, test_database):
    with Session(test_database) as session:
        session.add(ExchangeRate(base_currency="KRW", target_currency="USD", rate_date=date.today() - timedelta(days=1),
                                 rate=Decimal("0.0008"), source="test"))
        session.commit()
    rule = client.post("/api/v1/alerts/rules", json={
        "target_currency": "USD", "alert_type": "won_cost_at_or_below", "threshold": "1300",
    }).json()
    endpoint = f"/api/v1/alerts/rules/{rule['id']}"
    assert client.patch(endpoint, json={"enabled": False}).json()["enabled"] is False
    with Session(test_database) as session:
        session.add(ExchangeRate(base_currency="KRW", target_currency="USD", rate_date=date.today(),
                                 rate=Decimal("0.00085"), source="test"))
        session.commit()
    assert client.post("/api/v1/alerts/evaluate").json() == {"created": 0}
    assert client.patch(endpoint, json={"enabled": True}).json()["enabled"] is True
    assert len(client.get("/api/v1/alerts").json()) == 2
    assert client.post("/api/v1/alerts/evaluate").json() == {"created": 0}
    assert client.delete(endpoint).status_code == 204
    assert client.get("/api/v1/alerts/rules?base_currency=KRW&target_currency=USD").json() == []
    with Session(test_database) as session:
        history = list(session.scalars(select(AlertEvent)))
        assert len(history) == 2
        assert all(event.rule_id is None for event in history)


def test_price_rule_validation_and_missing_rule_errors(client):
    for base, target in [("USD", "KRW"), ("KRW", "KRW"), ("KRW", "XYZ")]:
        response = client.post("/api/v1/alerts/rules", json={
            "base_currency": base, "target_currency": target,
            "alert_type": "won_cost_at_or_below", "threshold": "1300",
        })
        assert response.status_code == 422
    assert client.patch("/api/v1/alerts/rules/999", json={"enabled": False}).status_code == 404
    assert client.delete("/api/v1/alerts/rules/999").status_code == 404


def test_price_rule_waits_for_collected_quote(client):
    response = client.post("/api/v1/alerts/rules", json={
        "target_currency": "JPY", "alert_type": "won_cost_at_or_below", "threshold": "9",
    })
    assert response.status_code == 201
    assert client.get("/api/v1/alerts").json() == []
