# debug_liquidity_usdjpy.py

from pprint import pprint
from datetime import datetime, timezone

import pandas as pd

from pa_engine.db.candles import load_m1_candles
from pa_engine.pa.features import FeatureConfig, add_core_features
from pa_engine.pa.structure import detect_swings, label_swings
from pa_engine.pa.liquidity import (
    detect_equal_highs_lows,
    detect_asia_range_liquidity,
    detect_sweeps_of_levels,
    LiquidityType,
    SweepSide,
)


def main():
    instrument = "USDJPY"
    hours_back = 24

    end = datetime.now(timezone.utc)
    start = end - pd.Timedelta(hours=hours_back)

    df_m1 = load_m1_candles(instrument, start, end)
    if df_m1.empty:
        print("No M1 data loaded.")
        return

    cfg = FeatureConfig()
    df_feat = add_core_features(df_m1, cfg)

    # Swings on M5 for equal highs/lows (you can also use M15)
    from pa_engine.db.resampler import resample_tf
    df_m5 = resample_tf(df_feat, "M5")
    df_m5 = add_core_features(df_m5, cfg)

    swings_m5 = label_swings(detect_swings(df_m5, left=2, right=2))

    # Liquidity levels from swings
    liq_levels_swings = detect_equal_highs_lows(
        swings=swings_m5,
        tolerance_abs=0.0005,  # adjust for JPY if needed (e.g., 0.01)
        min_touches=2,
    )

    # Asia range liquidity (from M1)
    liq_levels_asia = detect_asia_range_liquidity(df_feat)

    all_liq_levels = liq_levels_swings + liq_levels_asia

    sweeps = detect_sweeps_of_levels(df_feat, all_liq_levels, lookback_bars=500)

    print(f"=== Liquidity Levels for {instrument} ===")
    for lvl in all_liq_levels:
        print(
            f"{lvl.ts} | {lvl.type.value:10s} | price={lvl.price:.5f} | "
            f"touches={lvl.touches}"
        )

    print("\n=== Recent Sweeps ===")
    for sw in sweeps[-15:]:
        print(
            f"{sw.ts} | level_type={sw.level.type.value:10s} | "
            f"side={sw.side.value:9s} | "
            f"level={sw.level.price:.5f} | "
            f"high={sw.high:.5f} low={sw.low:.5f} close={sw.close:.5f}"
        )


if __name__ == "__main__":
    main()
