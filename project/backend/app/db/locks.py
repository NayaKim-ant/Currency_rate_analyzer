from sqlalchemy import text
from sqlalchemy.orm import Session


def lock_market_writes(session: Session) -> None:
    """Serialize collector/analysis read-modify-write transactions on PostgreSQL.

    The transaction releases the lock on commit or rollback, including failures.
    SQLite test sessions remain single-writer and need no advisory lock.
    """
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(7314126501)"))
