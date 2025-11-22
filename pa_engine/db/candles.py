from datetime import datetime
from typing import Optional
import pandas as pd

from pa_engine.db.connection import get_sqlalchemy_engine
from pa_engine.config.loader import build_app_config

_cfg = build_app_config()


def load_m1_candles(
    instrument: str,
    start_ts_utc: datetime,
    end_ts_utc: datetime,
) -> pd.DataFrame:
    """
    Returns M1 candles [start_ts_utc, end_ts_utc) for a given instrument,
    merging historical + live tables, with canonical columns:
      index: ts_utc (datetime, UTC)
      columns:
        - instrument
        - open, high, low, close
        - norm_volume
        - data_source ('historical' or 'live')

    Session tagging is NOT done here anymore; it is applied later in
    pa_engine.pa.features.add_core_features via infer_session()/session_for_hour.
    """
    sql = f"""
    WITH combined AS (
        -- Historical candles (no tick volume)
        SELECT
            instrument,
            "timestamp" AT TIME ZONE 'UTC' AS ts_utc,
            bid_open  AS open,
            bid_high  AS high,
            bid_low   AS low,
            bid_close AS close,
            volume::numeric AS norm_volume,
            'historical'::text AS data_source
        FROM { _cfg.database.historical_table }
        WHERE instrument = %(instrument)s
          AND "timestamp" >= %(start)s
          AND "timestamp" <  %(end)s

        UNION ALL

        -- Live candles (have tick_count)
        SELECT
            instrument,
            "timestamp" AT TIME ZONE 'UTC' AS ts_utc,
            bid_open  AS open,
            bid_high  AS high,
            bid_low   AS low,
            bid_close AS close,
            COALESCE(tick_count::numeric, volume::numeric) AS norm_volume,
            'live'::text AS data_source
        FROM { _cfg.database.live_table }
        WHERE instrument = %(instrument)s
          AND "timestamp" >= %(start)s
          AND "timestamp" <  %(end)s
    )
    SELECT
        instrument,
        ts_utc,
        open, high, low, close,
        norm_volume,
        data_source
    FROM combined
    ORDER BY ts_utc;
    """

    engine = get_sqlalchemy_engine()
    df = pd.read_sql_query(
        sql,
        engine,
        params={"instrument": instrument, "start": start_ts_utc, "end": end_ts_utc},
        parse_dates=["ts_utc"],
    )

    if df.empty:
        return df

    # Set index to ts_utc and sort
    df = df.set_index("ts_utc").sort_index()
    return df
