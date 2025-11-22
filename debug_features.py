from datetime import datetime, timedelta, timezone

import pandas as pd

from pa_engine.db.candles import load_m1_candles
from pa_engine.db.resampler import resample_tf
from pa_engine.pa.features import (
    FeatureConfig,
    add_core_features,
    compute_daily_levels,
    compute_session_levels,
)

INSTRUMENT = "USDJPY"  # change if you want


def main():
    # 1) Time window: last 6 hours
    end = datetime.now(timezone.utc)
    start = end.replace(hour=0, minute=0, second=0, microsecond=0)

    print(f"Loading M1 candles for {INSTRUMENT} from {start} to {end} (UTC)")
    df_m1 = load_m1_candles(INSTRUMENT, start, end)

    if df_m1.empty:
        print("No M1 candles returned for this window (maybe weekend or no data).")
        return

    print("\n=== M1 raw (last 5 rows) ===")
    print(df_m1.tail(5)[["instrument", "open", "high", "low", "close", "norm_volume", "session"]])

    # 2) Build higher TFs
    df_m5 = resample_tf(df_m1, "M5")
    df_m15 = resample_tf(df_m1, "M15")
    df_h1 = resample_tf(df_m1, "H1")

    print(f"\nM1 rows:  {len(df_m1)}")
    print(f"M5 rows:  {len(df_m5)}")
    print(f"M15 rows: {len(df_m15)}")
    print(f"H1 rows:  {len(df_h1)}")

    # 3) Add features
    cfg = FeatureConfig(
        atr_period=14,
        ema_periods=(20, 50),
        donchian_periods=(20, 50),
    )

    df_m1_f = add_core_features(df_m1, cfg)
    df_m15_f = add_core_features(df_m15, cfg)
    df_h1_f = add_core_features(df_h1, cfg)

    # 4) Print some sample feature values

    print("\n=== M15 features (last 5 rows) ===")
    cols_m15 = [
        "open", "high", "low", "close",
        f"ema_{cfg.ema_periods[0]}",
        f"ema_{cfg.ema_periods[1]}",
        f"atr_{cfg.atr_period}",
        f"donchian_high_{cfg.donchian_periods[0]}",
        f"donchian_low_{cfg.donchian_periods[0]}",
    ]
    print(df_m15_f.tail(5)[cols_m15])

    print("\n=== H1 features (last 5 rows) ===")
    cols_h1 = [
        "open", "high", "low", "close",
        f"ema_{cfg.ema_periods[0]}",
        f"ema_{cfg.ema_periods[1]}",
        f"atr_{cfg.atr_period}",
    ]
    print(df_h1_f.tail(5)[cols_h1])

    # 5) Daily and session levels from M1
    daily_levels = compute_daily_levels(df_m1)
    session_levels = compute_session_levels(df_m1)

    print("\n=== Daily levels ===")
    print(daily_levels)

    print("\n=== Session levels (current day) ===")
    print(session_levels)


if __name__ == "__main__":
    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", 20)
    main()
