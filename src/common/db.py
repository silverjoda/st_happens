"""SQLAlchemy engine, session factory, and schema bootstrap."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from src.common.settings import get_database_url


Base = declarative_base()

_engine: Engine | None = None
_session_local: sessionmaker[Session] | None = None
_engine_url: str | None = None


def _get_engine() -> Engine:
    global _engine
    _get_session_local()
    assert _engine is not None
    return _engine


def _get_session_local() -> sessionmaker[Session]:
    global _engine, _session_local, _engine_url

    url = get_database_url()
    if _engine is None or _session_local is None or _engine_url != url:
        _engine = create_engine(url, future=True)
        _session_local = sessionmaker(
            bind=_engine, autocommit=False, autoflush=False, class_=Session, future=True
        )
        _engine_url = url

    return _session_local


def create_schema() -> None:
    """Create all configured tables when they do not exist."""
    from src.common import models  # noqa: F401

    Base.metadata.create_all(bind=_get_engine())


@contextmanager
def session_scope() -> Iterator[Session]:
    """Yield a transactional SQLAlchemy session."""
    session = _get_session_local()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
