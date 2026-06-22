"""
Database connection and session management (read-only credential access).
Migrations are owned by the API microservice; this service only reads.
"""
import logging
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from helpers.get_secret import get_secret

logger = logging.getLogger(__name__)

Base = declarative_base()

SessionLocal: sessionmaker = None
engine = None


def get_database_url() -> str:
    """Get database URL from Secret Manager or environment variable."""
    try:
        db_url = get_secret("POSTGRES_URL")
        if db_url:
            return db_url
    except Exception as e:
        logger.warning("Failed to get POSTGRES_URL from Secret Manager: %s", e)

    db_url = os.getenv("POSTGRES_URL")
    if db_url:
        return db_url

    raise ValueError("POSTGRES_URL not found in Secret Manager or environment variables")


def init_database():
    """Initialize database connection and session factory (idempotent)."""
    global SessionLocal, engine
    if engine is not None:
        return
    database_url = get_database_url()
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        echo=False,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Get a database session."""
    if SessionLocal is None:
        init_database()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
