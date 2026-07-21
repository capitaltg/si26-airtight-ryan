"""Engine and session factory for the runtime DB.

``create_engine`` does not open a connection, so importing this offline (e.g. in
unit tests that override the ``get_db`` dependency) is free. The real app reads
``DATABASE_URL`` from the environment; the schema is owned by Alembic.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, committed on success."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
