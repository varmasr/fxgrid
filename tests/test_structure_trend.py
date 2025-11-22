# tests/test_structure_trend.py

from datetime import datetime, timedelta

import pandas as pd

from pa_engine.pa.structure import detect_swings, label_swings, swings_to_dataframe
from pa_engine.pa.trend import infer_trend_state, TrendStateEnum


def make_uptrend_with_swings() -> pd.DataFrame:
    """
    Small synthetic uptrend with obvious swing highs/lows.
    Pattern (close):
      100, 101, 102, 101, 103, 104, 103, 105
    """
    start = datetime(2025, 1, 1, 0, 0)
    idx = [start + timedelta(minutes=i) for i in range(8)]

    close = pd.Series([100, 101, 102, 101, 103, 104, 103, 105], index=idx)
    high  = close + 1
    low   = close - 1
    open_ = close  # doesn’t matter here

    df = pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low":  low,
            "close": close,
            "norm_volume": 1000,
        },
        index=pd.to_datetime(idx),
    )

    # Simple EMA so trend engine has something
    df["ema_50"] = df["close"].ewm(span=3, adjust=False).mean()
    return df


def make_downtrend_with_swings() -> pd.DataFrame:
    """
    Small synthetic downtrend with obvious swings.
    Pattern (close):
      105, 104, 103, 104, 102, 101, 102, 100
    """
    start = datetime(2025, 1, 1, 0, 0)
    idx = [start + timedelta(minutes=i) for i in range(8)]

    close = pd.Series([105, 104, 103, 104, 102, 101, 102, 100], index=idx)
    high  = close + 1
    low   = close - 1
    open_ = close

    df = pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low":  low,
            "close": close,
            "norm_volume": 1000,
        },
        index=pd.to_datetime(idx),
    )

    df["ema_50"] = df["close"].ewm(span=3, adjust=False).mean()
    return df


def test_detect_swings_on_uptrend():
    df = make_uptrend_with_swings()
    swings = detect_swings(df, left=1, right=1)
    labeled = label_swings(swings)
    df_sw = swings_to_dataframe(labeled)

    # There MUST be some swings here
    assert not df_sw.empty
    assert {"HIGH", "LOW"}.issuperset(set(df_sw["type"].unique()))


def test_trend_state_uptrend():
    df = make_uptrend_with_swings()
    swings = label_swings(detect_swings(df, left=1, right=1))

    trend = infer_trend_state(df, swings, ema_col="ema_50", tf="M15")

    # For this tiny pattern, we mostly care that it's not UNCLEAR
    assert trend.state in {TrendStateEnum.UP, TrendStateEnum.RANGE}



def test_trend_state_downtrend():
    df = make_downtrend_with_swings()
    swings = label_swings(detect_swings(df, left=1, right=1))

    trend = infer_trend_state(df, swings, ema_col="ema_50", tf="M15")

    assert trend.state in {TrendStateEnum.DOWN, TrendStateEnum.RANGE}


from datetime import timezone
from pa_engine.db.candles import load_m1_candles
from pa_engine.db.resampler import resample_tf
from pa_engine.pa.features import FeatureConfig, add_core_features

def test_real_data_structure_trend_usdjpy():
    # Last 24h on M15 from DB
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=24)

    df_m1 = load_m1_candles("USDJPY", start, end)
    if df_m1.empty:
        # Weekend / no data – don't fail the test
        return

    df_m15 = resample_tf(df_m1, "M15")
    cfg = FeatureConfig()
    df_m15_f = add_core_features(df_m15, cfg)

    swings = label_swings(detect_swings(df_m15_f, left=2, right=2))
    trend = infer_trend_state(df_m15_f, swings, ema_col="ema_50", tf="M15")

    # Just assert we *have* some structure and a non-crashing trend
    assert len(swings) > 0
    assert trend.state in {
        TrendStateEnum.UP,
        TrendStateEnum.DOWN,
        TrendStateEnum.RANGE,
        TrendStateEnum.UNCLEAR,
    }
