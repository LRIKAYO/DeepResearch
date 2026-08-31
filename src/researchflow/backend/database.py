import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def require_database_url() -> str:
    database_url = os.getenv("RESEARCHFLOW_DATABASE_URL")
    if not database_url:
        raise RuntimeError("Missing required environment variable: RESEARCHFLOW_DATABASE_URL")
    return database_url


engine = create_engine(require_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
