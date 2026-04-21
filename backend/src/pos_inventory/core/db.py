"""SQLAlchemy 2.x engine + session (sync, psycopg3)."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from pos_inventory.core.config import get_settings

_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def engine():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(get_settings().db_dsn_sync, future=True, pool_pre_ping=True)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine


def session_factory() -> sessionmaker[Session]:
    engine()
    assert _SessionLocal is not None
    return _SessionLocal


def get_session() -> Iterator[Session]:
    sess = session_factory()()
    try:
        yield sess
        sess.commit()
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()
