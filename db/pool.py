"""Shared PostgreSQL connection pool for the auth and business modules."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Generator

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

logger = logging.getLogger(__name__)

_pool: ThreadedConnectionPool | None = None


def _postgres_url() -> str:
    raw = os.getenv("DATABASE_URL", "").strip()
    if not raw:
        raise RuntimeError(
            "DATABASE_URL is not set. Set it in .env (e.g. postgresql://user:pass@host:5432/dbname)."
        )
    # Strip Prisma-style ?schema=public suffix that psycopg2 does not accept.
    return raw.split("?", 1)[0]


def init_pool(min_conn: int = 2, max_conn: int = 10) -> None:
    """Initialize the global connection pool (called once at app startup)."""
    global _pool
    if _pool is not None:
        return
    url = _postgres_url()
    _pool = ThreadedConnectionPool(min_conn, max_conn, url)
    logger.info("PostgreSQL connection pool initialized (min=%d, max=%d).", min_conn, max_conn)


def close_pool() -> None:
    """Close all connections in the pool (called on app shutdown)."""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None
        logger.info("PostgreSQL connection pool closed.")


def get_connection():
    """Acquire a connection from the pool. Caller MUST call release_connection() afterwards."""
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call init_pool() at app startup.")
    return _pool.getconn()


def release_connection(conn) -> None:
    """Return a connection to the pool."""
    if _pool is not None and conn is not None:
        _pool.putconn(conn)


@contextmanager
def db_cursor(commit: bool = True, dict_cursor: bool = True) -> Generator:
    """Context manager that yields a cursor, auto-commits/rolls-back, and releases the conn.

    Usage:
        with db_cursor() as cur:
            cur.execute("SELECT ...")
            rows = cur.fetchall()
    """
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor if dict_cursor else None)
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        release_connection(conn)
