# tests/test_config_and_db.py

from pa_engine.config.loader import build_app_config
from pa_engine.db.connection import get_connection

def test_app_config_loads():
    cfg = build_app_config()
    assert cfg.database.host
    assert cfg.database.name
    assert cfg.database.live_table == "live_market_data_m1"
    assert cfg.database.historical_table == "market_data_m1"
    assert cfg.database.storage_timezone == "UTC"

def test_db_connection_and_now():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT NOW() AT TIME ZONE 'UTC';")
            row = cur.fetchone()
            assert row is not None
