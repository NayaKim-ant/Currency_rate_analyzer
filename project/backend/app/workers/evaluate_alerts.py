from app.db.session import SessionLocal
from app.services.alert_engine import evaluate_alert_rules


def main() -> None:
    with SessionLocal() as session:
        created_count = evaluate_alert_rules(session)
    print(f"Created {created_count} alert events")


if __name__ == "__main__":
    main()
