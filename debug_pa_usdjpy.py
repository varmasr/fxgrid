from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pprint import pprint

import pandas as pd

from pa_engine.db.candles import load_m1_candles
from pa_engine.db.resampler import resample_tf
from pa_engine.pa.features import (
    FeatureConfig,
    add_core_features,
    compute_daily_levels,
    compute_session_levels,
)
from pa_engine.pa.structure import detect_swings, label_swings, swings_to_dataframe
from pa_engine.pa.trend import infer_trend_state
from pa_engine.pa.order_blocks import (
    detect_order_blocks,
    order_blocks_to_dataframe,
    score_order_blocks,
)


INSTRUMENT = "USDJPY"
TIMEFRAMES = ["M1", "M5", "M15", "H1"]


def build_tf_frames(df_m1: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Build TF-specific dataframes (with core features) for M1, M5, M15, H1.
    """
    cfg = FeatureConfig(
        atr_period=14,
        ema_periods=(20, 50),
        donchian_periods=(20, 50),
    )

    tf_frames: dict[str, pd.DataFrame] = {}

    # M1
    df_m1_f = add_core_features(df_m1, cfg)
    tf_frames["M1"] = df_m1_f

    # Higher TFs
    for tf in ["M5", "M15", "H1"]:
        df_tf = resample_tf(df_m1_f, tf)
        df_tf_f = add_core_features(df_tf, cfg)
        tf_frames[tf] = df_tf_f

    return tf_frames


def analyze_tf(tf: str, df_tf: pd.DataFrame):
    """
    For a given timeframe DF:
      - detect swings
      - infer trend
      - detect and score OBs
      - print summary
    """
    print(f"\n========== {INSTRUMENT} | {tf} ==========")

    if df_tf.empty:
        print("No data for this TF.")
        return

    # Last few candles
    print("\nLast 5 candles:")
    print(df_tf[["open", "high", "low", "close"]].tail(5))

    # Swings
    swings = label_swings(detect_swings(df_tf, left=2, right=2))
    df_sw = swings_to_dataframe(swings)

    print(f"\nSwings detected: {len(swings)}")
    if not df_sw.empty:
        print("Last 5 swings:")
        print(df_sw.tail(5))
    else:
        print("No swings detected on this TF (may be too little data or very smooth trend).")

    # Trend
    trend = infer_trend_state(df_tf, swings, ema_col="ema_50", tf=tf)
    print(f"\nTrend state: {trend.state.value}")
    print(f"Trend reason: {trend.reason}")

    # OBs
    obs = detect_order_blocks(df_tf, swings, tf=tf)
    print(f"\nOrder Blocks detected: {len(obs)}")

    if obs:
        scored_obs = score_order_blocks(df_tf, obs, trend=trend, atr_col=f"atr_14")
        df_obs = order_blocks_to_dataframe(scored_obs)

        print("\nTop 3 OBs by score:")
        # Sort already done in score_order_blocks, but to be safe:
        df_obs_sorted = df_obs.sort_values("score", ascending=False).head(3)
        print(df_obs_sorted[["tf", "type", "low", "high", "body_low", "body_high", "broken_level", "score"]])
    else:
        print("No OBs detected on this TF.")


def main():
    # 1) Time window: last 24 hours
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=24)

    print(f"Loading M1 candles for {INSTRUMENT} from {start} to {end} (UTC)")
    df_m1 = load_m1_candles(INSTRUMENT, start, end)

    if df_m1.empty:
        print("No M1 candles returned (weekend or no data).")
        return

    print(f"Loaded {len(df_m1)} M1 rows.")

    # 2) Daily & Session levels from M1
    daily_levels = compute_daily_levels(df_m1)
    session_levels = compute_session_levels(df_m1)

    print("\n=== Daily Levels ===")
    pprint(daily_levels)

    print("\n=== Session Levels (current day) ===")
    pprint(session_levels)

    # 3) Build TF frames with features
    tf_frames = build_tf_frames(df_m1)
    from pa_engine.pa.fvg import detect_fvgs, fvgs_to_dataframe
    # 4) Analyze each TF
    for tf in TIMEFRAMES:
        analyze_tf(tf, tf_frames[tf])
        fvgs = detect_fvgs(tf_frames[tf], tf=tf, atr_col="atr_14", min_size_frac_atr=0.1)
        df_fvg = fvgs_to_dataframe(fvgs)
        print(f"\nFVGs detected on {tf}: {len(fvgs)}")
        if not df_fvg.empty:
            print("Last 5 FVGs:")
            print(df_fvg.tail(5))


    

    # inside analyze_tf(...)
    

if __name__ == "__main__":
    pd.set_option("display.width", 180)
    pd.set_option("display.max_columns", 20)
    main()
