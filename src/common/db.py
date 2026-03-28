"""SQLAlchemy engine, session factory, and schema bootstrap."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from src.common.settings import get_database_url


Base = declarative_base()

engine = create_engine(get_database_url(), future=True)
SessionLocal = sessionmaker(
    bind=engine, autocommit=False, autoflush=False, class_=Session, future=True
)


def create_schema() -> None:
    """Create all configured tables when they do not exist."""
    from src.common import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Yield a transactional SQLAlchemy session."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
