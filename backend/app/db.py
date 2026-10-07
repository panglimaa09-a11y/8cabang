"""Database engine and session factory.

Serverless note (Vercel): function instances are ephemeral, so the app must
NOT pool connections itself. We use NullPool and let Supabase Supavisor
(transaction mode, port 6543) do the actual pooling. pool_pre_ping is
unnecessary with NullPool (every checkout opens a fresh connection) and only
adds one roundtrip per request.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

from .config import settings

engine = None
SessionLocal = None

if settings.DATABASE_URL:
    engine = create_engine(
        settings.DATABASE_URL,
        poolclass=NullPool,
        future=True,
        connect_args={"connect_timeout": 10},
    )
    SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False, future=True)


def get_session() -> Session:
    """Create a new ORM session. Raises if DATABASE_URL is not configured."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")
    return SessionLocal()
