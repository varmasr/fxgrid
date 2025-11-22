from pa_engine.db.connection import get_connection

with get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT NOW() AT TIME ZONE 'UTC';")
        print(cur.fetchone())

with get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables
            WHERE table_name IN (
                'live_market_data_m1',
                'market_data_m1',
                'macro_calendar_events',
                'pa_snapshots',
                'trade_plans',
                'backtest_runs',
                'backtest_trades'
            );
        """)
        print(cur.fetchall())