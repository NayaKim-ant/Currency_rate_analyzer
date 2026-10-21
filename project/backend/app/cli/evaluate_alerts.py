"""Evaluate alert rules against the latest market events and exchange rates."""

from app.db.session import SessionLocal
from app.services.alerts.engine import evaluate_alert_rules


def main() -> None:
    with SessionLocal() as session:
        created_count = evaluate_alert_rules(session)
    print(f"Created {created_count} alert events")


if __name__ == "__main__":
    main()
