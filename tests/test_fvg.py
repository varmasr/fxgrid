# tests/test_fvg.py

from datetime import datetime, timedelta

import pandas as pd

from pa_engine.pa.fvg import detect_fvgs, fvgs_to_dataframe, FVGDirection


def _make_simple_fvg_df() -> pd.DataFrame:
    """
    Construct a small price series with:

      - Bullish FVG between candle 0 and 2:
          candle 0 high = 101
          candle 2 low  = 103  (103 > 101)

      - Bearish FVG between candle 3 and 5:
          candle 3 low  = 95
          candle 5 high = 93  (93 < 95)

      - Then a fill of the bullish FVG later.
    """
    start = datetime(2025, 1, 1, 0, 0)
    idx = [start + timedelta(minutes=i) for i in range(8)]

    # Define close and open so highs/lows form the pattern we want.
    close = pd.Series(
        [
            100,  # 0
            101,  # 1
            104,  # 2  (low above previous high -> bullish FVG)
            96,   # 3
            95,   # 4
            92,   # 5  (high below previous low -> bearish FVG)
            100,  # 6 - retraces down into bullish FVG zone
            98,   # 7
        ],
        index=idx,
    )
    open_ = close.shift(1).fillna(close.iloc[0])

    high = pd.concat([open_, close], axis=1).max(axis=1) + 1.0
    low = pd.concat([open_, close], axis=1).min(axis=1) - 1.0

    # Make sure we set exact values for the key candles:
    # candle 0: high = 101
    high.iloc[0] = 101
    low.iloc[0] = 99

    # candle 2: low = 103  (=> low2 > high0)
    low.iloc[2] = 103
    high.iloc[2] = 105

    # candle 3: low = 95
    low.iloc[3] = 95
    high.iloc[3] = 97

    # candle 5: high = 93 (=> high5 < low3)
    high.iloc[5] = 93
    low.iloc[5] = 91

    # candle 6: low <= bullish gap_low to fill bullish FVG later
    # bullish gap_low = high[0] = 101, so set low[6] <= 101
    low.iloc[6] = 100
    high.iloc[6] = 102

    df = pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
        },
        index=pd.to_datetime(idx),
    )

    # Simple pseudo-ATR
    df["atr_14"] = (df["high"] - df["low"]).rolling(3, min_periods=1).mean()
    return df


def test_detect_fvgs_basic():
    df = _make_simple_fvg_df()
    fvgs = detect_fvgs(df, tf="M15", atr_col="atr_14", min_size_frac_atr=0.0)

    assert len(fvgs) >= 2

    df_fvg = fvgs_to_dataframe(fvgs)

    # We should have both bullish and bearish FVGs
    directions = set(df_fvg["direction"].unique())
    assert FVGDirection.BULLISH.value in directions
    assert FVGDirection.BEARISH.value in directions

    # Check that at least one bullish FVG is filled (by candle 6)
    bullish = df_fvg[df_fvg["direction"] == FVGDirection.BULLISH.value]
    assert not bullish.empty
    assert bullish["is_filled"].any()
