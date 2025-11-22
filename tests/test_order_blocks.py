# tests/test_order_blocks.py

from datetime import datetime, timedelta

import pandas as pd

from pa_engine.pa.structure import LabeledSwingPoint, SwingType
from pa_engine.pa.order_blocks import (
    detect_bos_from_swings,
    detect_order_blocks,
    OrderBlockType,
)


def _make_simple_upmove_df() -> pd.DataFrame:
    """
    Small sequence with:
      - some noise
      - a clear down candle
      - then strong push up (up BOS)

    We'll not overfit; just need a consistent pattern
    where OB finder has a bearish candle before an up break.
    """
    start = datetime(2025, 1, 1, 0, 0)
    idx = [start + timedelta(minutes=i) for i in range(9)]

    # close series is arbitrary but trending up with one clear down candle
    close = pd.Series([100, 101, 102, 101, 99, 101, 104, 106, 107], index=idx)
    open_ = pd.Series([100, 100.5, 101.5, 101.8, 100.5, 100.8, 103, 105, 106.5], index=idx)

    high = pd.concat(
        [open_, close], axis=1
    ).max(axis=1) + 0.5  # small wick above
    low = pd.concat(
        [open_, close], axis=1
    ).min(axis=1) - 0.5  # small wick below

    df = pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "norm_volume": 1000,
        },
        index=pd.to_datetime(idx),
    )
    return df


def test_bos_detection_from_swings():
    df = _make_simple_upmove_df()

    # Manually define a sequence of swings:
    # let's say we consider:
    #   - first local high at index 2
    #   - a deeper low
    #   - then a higher high at index 7 (BOS up)
    swings = [
        LabeledSwingPoint(
            ts=df.index[2],
            price=float(df["high"].iloc[2]),
            type=SwingType.HIGH,
            index=2,
            strength=2,
            rel_label=None,  # first high
        ),
        LabeledSwingPoint(
            ts=df.index[4],
            price=float(df["low"].iloc[4]),
            type=SwingType.LOW,
            index=4,
            strength=2,
            rel_label=None,  # first low
        ),
        LabeledSwingPoint(
            ts=df.index[7],
            price=float(df["high"].iloc[7]),
            type=SwingType.HIGH,
            index=7,
            strength=2,
            rel_label="HH",  # breaks above the first high
        ),
    ]

    bos_list = detect_bos_from_swings(swings)
    assert len(bos_list) == 1
    bos = bos_list[0]
    assert bos.bos_type.value == "UP"
    assert bos.idx == 7
    assert bos.broken_level == swings[0].price


def test_order_block_detection_demand():
    df = _make_simple_upmove_df()

    # Same swings as above
    swings = [
        LabeledSwingPoint(
            ts=df.index[2],
            price=float(df["high"].iloc[2]),
            type=SwingType.HIGH,
            index=2,
            strength=2,
            rel_label=None,
        ),
        LabeledSwingPoint(
            ts=df.index[4],
            price=float(df["low"].iloc[4]),
            type=SwingType.LOW,
            index=4,
            strength=2,
            rel_label=None,
        ),
        LabeledSwingPoint(
            ts=df.index[7],
            price=float(df["high"].iloc[7]),
            type=SwingType.HIGH,
            index=7,
            strength=2,
            rel_label="HH",
        ),
    ]

    obs = detect_order_blocks(df, swings, tf="M15", max_lookback_bars=10)
    # We expect at least one demand OB
    assert len(obs) >= 1

    demand_obs = [ob for ob in obs if ob.type == OrderBlockType.DEMAND]
    assert len(demand_obs) >= 1

    # The OB should come from a bearish candle before index 7
    # There is a clear bearish candle around index 4
    ob = demand_obs[0]
    assert ob.idx < 7
    assert ob.low <= ob.high
    assert ob.body_low <= ob.body_high
