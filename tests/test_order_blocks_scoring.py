# tests/test_order_block_scoring.py

from datetime import datetime, timedelta

import pandas as pd

from pa_engine.pa.order_blocks import OrderBlock, OrderBlockType, score_order_block
from pa_engine.pa.trend import TrendState, TrendStateEnum


def _make_dummy_tf_df(n: int = 100) -> pd.DataFrame:
    start = datetime(2025, 1, 1, 0, 0)
    idx = [start + timedelta(minutes=i) for i in range(n)]

    base = pd.Series(range(100, 100 + n), index=idx)
    close = base + 0.5
    open_ = base - 0.5
    high = close + 0.3
    low = open_ - 0.3

    df = pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
        },
        index=pd.to_datetime(idx),
    )
    # Simple ATR proxy
    df["atr_14"] = (df["high"] - df["low"]).rolling(14, min_periods=1).mean()
    return df


def test_ob_scoring_basic():
    df = _make_dummy_tf_df(200)

    # Create a demand OB about 1 ATR below current price, fairly recent
    ob = OrderBlock(
        tf="M15",
        type=OrderBlockType.DEMAND,
        ts=df.index[-20],
        idx=len(df) - 20,
        low=float(df["low"].iloc[-20]),
        high=float(df["high"].iloc[-20]),
        body_low=float(min(df["open"].iloc[-20], df["close"].iloc[-20])),
        body_high=float(max(df["open"].iloc[-20], df["close"].iloc[-20])),
        bos_ts=df.index[-10],
        bos_idx=len(df) - 10,
        broken_level=float(df["high"].iloc[-30]),
    )

    trend = TrendState(
        state=TrendStateEnum.UP,
        reason="Test uptrend",
        tf="M15",
    )

    scored = score_order_block(df, ob, trend=trend, atr_col="atr_14")
    assert scored.score is not None
    assert 0.0 <= scored.score <= 100.0
    assert "trend_score" in scored.score_components
