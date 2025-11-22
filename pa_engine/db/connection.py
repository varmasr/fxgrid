# pa_engine/db/connection.py

from contextlib import contextmanager
from typing import Iterator

import psycopg2
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from pa_engine.config.loader import build_app_config

_cfg = build_app_config()

# ---------- DSN helpers ----------

def _make_dsn_string() -> str:
    db = _cfg.database
    return (
        f"host={db.host} "
        f"port={db.port} "
        f"dbname={db.name} "
        f"user={db.user} "
        f"password={db.password}"
    )

# ---------- psycopg2 connection (still used) ----------

@contextmanager
def get_connection() -> Iterator[psycopg2.extensions.connection]:
    """
    Low-level psycopg2 connection.
    Useful for non-pandas operations, DDL, etc.
    """
    conn = psycopg2.connect(dsn=_make_dsn_string())
    try:
        # Optional: set statement timeout from config
        with conn.cursor() as cur:
            cur.execute(
                f"SET statement_timeout = {_cfg.database.statement_timeout_ms};"
            )
        yield conn
    finally:
        conn.close()

# ---------- SQLAlchemy engine for pandas.read_sql_query ----------

_engine: Engine | None = None

def get_sqlalchemy_engine() -> Engine:
    """
    Lazily create and cache a SQLAlchemy engine for use with pandas.read_sql_query.
    """
    global _engine
    if _engine is None:
        db = _cfg.database
        # postgresql+psycopg2 connection URL
        url = f"postgresql+psycopg2://{db.user}:{db.password}@{db.host}:{db.port}/{db.name}"
        _engine = create_engine(url)
    return _engine
