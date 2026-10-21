from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.currencies import HOME_CURRENCY
from app.db.locks import lock_market_writes
from app.db.session import get_db
from app.models.alerts import AlertEvent, AlertRule
from app.schemas.alerts import AlertRuleCreate, AlertRuleRead, AlertRuleUpdate
from app.services.alerts.engine import evaluate_alert_rules

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.post("/rules", response_model=AlertRuleRead, status_code=201)
def create_alert_rule(payload: AlertRuleCreate, db: Session = Depends(get_db)) -> AlertRule:
    rule = AlertRule(
        base_currency=payload.base_currency.upper(),
        target_currency=payload.target_currency.upper(),
        alert_type=payload.alert_type,
        threshold=payload.threshold,
        lookback_days=payload.lookback_days,
    )
    db.add(rule)
    db.flush()
    evaluate_alert_rules(db)
    db.refresh(rule)
    return rule


@router.get("/rules", response_model=list[AlertRuleRead])
def list_alert_rules(
    base_currency: str | None = Query(default=None, min_length=3, max_length=3),
    target_currency: str | None = Query(default=None, min_length=3, max_length=3),
    db: Session = Depends(get_db),
) -> list[AlertRule]:
    statement = select(AlertRule).order_by(AlertRule.created_at.desc(), AlertRule.id.desc())
    if base_currency:
        statement = statement.where(AlertRule.base_currency == base_currency.upper())
    if target_currency:
        statement = statement.where(AlertRule.target_currency == target_currency.upper())
    return list(db.scalars(statement))


@router.patch("/rules/{rule_id}", response_model=AlertRuleRead)
def update_alert_rule(rule_id: int, payload: AlertRuleUpdate, db: Session = Depends(get_db)) -> AlertRule:
    lock_market_writes(db)
    rule = db.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    rule.enabled = payload.enabled
    db.flush()
    evaluate_alert_rules(db)
    db.refresh(rule)
    return rule


@router.delete("/rules/{rule_id}", status_code=204)
def delete_alert_rule(rule_id: int, db: Session = Depends(get_db)) -> Response:
    lock_market_writes(db)
    rule = db.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    # Keep past occurrences as history when their rule is removed.
    db.execute(update(AlertEvent).where(AlertEvent.rule_id == rule_id).values(rule_id=None))
    db.delete(rule)
    db.commit()
    return Response(status_code=204)


@router.post("/evaluate")
def check_alert_rules(db: Session = Depends(get_db)) -> dict[str, int]:
    return {"created": evaluate_alert_rules(db)}


@router.get("")
def list_alert_events(
    target_currency: str | None = Query(default=None, min_length=3, max_length=3),
    base_currency: str = Query(default=HOME_CURRENCY, min_length=3, max_length=3),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    statement = select(AlertEvent).where(AlertEvent.base_currency == base_currency.upper()).order_by(AlertEvent.fired_at.desc(), AlertEvent.id.desc()).limit(limit)
    if target_currency:
        statement = statement.where(AlertEvent.target_currency == target_currency.upper())
    return [
        {
            "id": event.id,
            "base_currency": event.base_currency,
            "target_currency": event.target_currency,
            "alert_type": event.alert_type,
            "measured_value": event.measured_value,
            "message": event.message,
            "fired_at": event.fired_at,
            "resolved_at": event.resolved_at,
        }
        for event in db.scalars(statement)
    ]
