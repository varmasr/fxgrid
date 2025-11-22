from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from pa_engine.db.candles import load_m1_candles
from pa_engine.db.resampler import resample_tf
from pa_engine.pa.features import FeatureConfig, add_core_features
from pa_engine.pa.fvg import detect_fvgs, fvgs_to_dataframe, FVGDirection

# ===== CONFIG =====
INSTRUMENT = "USDJPY"
TF = "M15"              # Change to "M5", "H1", etc. if you want
HOURS_BACK = 24         # How many hours of data to load
MAX_FVGS_TO_PRINT = 5   # How many recent FVGs to inspect
MIN_SIZE_FRAC_ATR = 0.0 # 0.1 to filter tiny gaps, 0.0 to see all


def build_tf_df(df_m1: pd.DataFrame, tf: str) -> pd.DataFrame:
    """
    Resample M1 to target TF and add core features (including ATR).
    """
    cfg = FeatureConfig(
        atr_period=14,
        ema_periods=(20, 50),
        donchian_periods=(20, 50),
    )

    # First add features on M1 (so resampled series have those aggregates too)
    df_m1_f = add_core_features(df_m1, cfg)

    if tf == "M1":
        return df_m1_f

    df_tf = resample_tf(df_m1_f, tf)
    df_tf_f = add_core_features(df_tf, cfg)
    return df_tf_f


def print_candle_block(df_tf: pd.DataFrame, i: int, label: str) -> None:
    """
    Pretty-print a single candle at position i.
    """
    if i < 0 or i >= len(df_tf):
        print(f"{label}: index {i} out of range")
        return

    row = df_tf.iloc[i]
    ts = df_tf.index[i]
    print(
        f"{label} idx={i:4d} ts={ts} | "
        f"O={row['open']:.3f} H={row['high']:.3f} "
        f"L={row['low']:.3f} C={row['close']:.3f}"
    )


def print_fvg_validation_for_one(df_tf: pd.DataFrame, fvg, idx_in_list: int) -> None:
    """
    Print a detailed validation block for a single FVG.
    """
    print("\n" + "=" * 80)
    print(
        f"FVG #{idx_in_list}: {fvg.direction.value} | tf={fvg.tf} | "
        f"{fvg.ts_start} -> {fvg.ts_end}"
    )
    # Precompute safe ATR text
    if fvg.size_atr is None:
        size_atr_txt = "nan"
    else:
        size_atr_txt = f"{fvg.size_atr:.3f}"

    print(
        f"gap_low={fvg.gap_low:.3f}  gap_high={fvg.gap_high:.3f}  "
        f"size_abs={fvg.size_abs:.3f}  size_atr={size_atr_txt}"
    )
    print(f"is_filled={fvg.is_filled}  filled_ts={fvg.filled_ts}")


    # Print the 3 pattern candles
    print("\nPattern candles (i, i+1, i+2):")
    print_candle_block(df_tf, fvg.idx_start, "i    ")
    print_candle_block(df_tf, fvg.idx_mid,   "i+1  ")
    print_candle_block(df_tf, fvg.idx_end,   "i+2  ")

    # Show the inequality check explicitly
    hi_i = float(df_tf["high"].iloc[fvg.idx_start])
    lo_i = float(df_tf["low"].iloc[fvg.idx_start])
    hi_2 = float(df_tf["high"].iloc[fvg.idx_end])
    lo_2 = float(df_tf["low"].iloc[fvg.idx_end])

    print("\nCondition check:")
    if fvg.direction == FVGDirection.BULLISH:
        print(f"  Bullish FVG condition: low[i+2] > high[i]")
        print(
            f"    low[i+2] = {lo_2:.3f}, high[i] = {hi_i:.3f}, "
            f"  => {lo_2:.3f} > {hi_i:.3f} == {lo_2 > hi_i}"
        )
    else:
        print(f"  Bearish FVG condition: high[i+2] < low[i]")
        print(
            f"    high[i+2] = {hi_2:.3f}, low[i] = {lo_i:.3f}, "
            f"  => {hi_2:.3f} < {lo_i:.3f} == {hi_2 < lo_i}"
        )

    # If filled, show the fill candle OHLC
    if fvg.is_filled and fvg.filled_ts is not None:
        print("\nFirst fill candle:")
        try:
            # Usually df index matches filled_ts exactly
            fill_loc = df_tf.index.get_loc(fvg.filled_ts)
            print_candle_block(df_tf, fill_loc, "fill")
            # Also check the fill condition numerically
            fill_row = df_tf.iloc[fill_loc]
            if fvg.direction == FVGDirection.BULLISH:
                print(
                    f"  Fill condition (bullish): low_fill <= gap_low "
                    f" => {fill_row['low']:.3f} <= {fvg.gap_low:.3f} == {fill_row['low'] <= fvg.gap_low}"
                )
            else:
                print(
                    f"  Fill condition (bearish): high_fill >= gap_high "
                    f" => {fill_row['high']:.3f} >= {fvg.gap_high:.3f} == {fill_row['high'] >= fvg.gap_high}"
                )
        except KeyError:
            print(f"  Could not locate filled_ts={fvg.filled_ts} in df index.")
    else:
        print("\nNo fill candle yet.")


def main():
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=HOURS_BACK)

    print(f"Loading {INSTRUMENT} M1 from {start} to {end} (UTC)")
    df_m1 = load_m1_candles(INSTRUMENT, start, end)

    if df_m1.empty:
        print("No M1 data returned (weekend or data gap). Exiting.")
        return

    print(f"Loaded {len(df_m1)} M1 rows.")

    # Build target TF dataframe
    df_tf = build_tf_df(df_m1, TF)
    if df_tf.empty:
        print(f"No data after resampling to {TF}. Exiting.")
        return

    print(f"Resampled to {TF}: {len(df_tf)} rows")

    # Detect FVGs
    fvgs = detect_fvgs(
        df_tf,
        tf=TF,
        atr_col="atr_14",
        min_size_frac_atr=MIN_SIZE_FRAC_ATR,
    )
    df_fvg = fvgs_to_dataframe(fvgs)

    print(f"\nDetected {len(fvgs)} FVGs on {INSTRUMENT} {TF}")
    if df_fvg.empty:
        print("No FVGs to print.")
        return

    print("\nLast few FVGs overview:")
    print(df_fvg.tail(min(10, len(df_fvg))))

    # Take the last N FVGs for detailed validation
    n_to_print = min(MAX_FVGS_TO_PRINT, len(fvgs))
    print(f"\n\nPrinting detailed validation for last {n_to_print} FVG(s):")

    for idx_in_list, fvg in enumerate(fvgs[-n_to_print:], start=1):
        print_fvg_validation_for_one(df_tf, fvg, idx_in_list)


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)
    main()
