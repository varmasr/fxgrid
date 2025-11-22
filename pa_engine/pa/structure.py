# pa_engine/pa/structure.py

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Literal

import pandas as pd


class SwingType(str, Enum):
    HIGH = "HIGH"
    LOW = "LOW"


@dataclass
class SwingPoint:
    """
    Represents a swing high/low on a given timeframe.
    """
    ts: pd.Timestamp
    price: float
    type: SwingType
    index: int          # integer location in original df
    strength: int       # left/right window size used


@dataclass
class LabeledSwingPoint(SwingPoint):
    """
    Swing with structure label relative to previous swing of same type.
    Labels: HH, HL, LH, LL (or None for first ones).
    """
    rel_label: Optional[str] = None  # 'HH','HL','LH','LL', None


def detect_swings(
    df: pd.DataFrame,
    left: int = 2,
    right: int = 2,
) -> List[SwingPoint]:
    """
    Detect swing highs and lows using a simple fractal rule:

      Swing HIGH at i:
        high[i] is strictly greater than highs of left bars
        AND >= highs of right bars

      Swing LOW at i:
        low[i] is strictly lower than lows of left bars
        AND <= lows of right bars

    Args:
        df: dataframe with index ts (datetime) and columns 'high', 'low'
        left:  number of bars to the left
        right: number of bars to the right

    Returns:
        List of SwingPoint sorted by index/time.
    """
    if df.empty:
        return []

    highs = df["high"]
    lows = df["low"]
    idxs = df.index

    swings: List[SwingPoint] = []

    # We need enough bars on both sides
    for i in range(left, len(df) - right):
        window_left = slice(i - left, i)
        window_right = slice(i + 1, i + 1 + right)

        hi = highs.iloc[i]
        lo = lows.iloc[i]

        left_high = highs.iloc[window_left]
        right_high = highs.iloc[window_right]

        left_low = lows.iloc[window_left]
        right_low = lows.iloc[window_right]

        is_swing_high = hi > left_high.max() and hi >= right_high.max()
        is_swing_low = lo < left_low.min() and lo <= right_low.min()

        ts = idxs[i]

        if is_swing_high:
            swings.append(
                SwingPoint(
                    ts=ts,
                    price=float(hi),
                    type=SwingType.HIGH,
                    index=i,
                    strength=max(left, right),
                )
            )

        if is_swing_low:
            swings.append(
                SwingPoint(
                    ts=ts,
                    price=float(lo),
                    type=SwingType.LOW,
                    index=i,
                    strength=max(left, right),
                )
            )

    # Sort by index (time)
    swings.sort(key=lambda s: s.index)
    return swings


def label_swings(swings: List[SwingPoint]) -> List[LabeledSwingPoint]:
    """
    For each swing, label it relative to the previous swing of the same type:

      For HIGH swings:
        HH: higher high (price > previous high)
        LH: lower high  (price < previous high)
        (equal can be treated as HH for now)

      For LOW swings:
        HL: higher low  (price > previous low)
        LL: lower low   (price < previous low)

    First swing of each type gets rel_label=None.
    """
    labeled: List[LabeledSwingPoint] = []
    last_high: Optional[SwingPoint] = None
    last_low: Optional[SwingPoint] = None

    for s in swings:
        if s.type == SwingType.HIGH:
            if last_high is None:
                rel = None
            else:
                rel = "HH" if s.price >= last_high.price else "LH"
            labeled.append(
                LabeledSwingPoint(
                    ts=s.ts,
                    price=s.price,
                    type=s.type,
                    index=s.index,
                    strength=s.strength,
                    rel_label=rel,
                )
            )
            last_high = s

        elif s.type == SwingType.LOW:
            if last_low is None:
                rel = None
            else:
                rel = "HL" if s.price >= last_low.price else "LL"
            labeled.append(
                LabeledSwingPoint(
                    ts=s.ts,
                    price=s.price,
                    type=s.type,
                    index=s.index,
                    strength=s.strength,
                    rel_label=rel,
                )
            )
            last_low = s

    # Already in time order since input swings were sorted
    return labeled


def swings_to_dataframe(labeled_swings: List[LabeledSwingPoint]) -> pd.DataFrame:
    """
    Helper: convert list of labeled swings into a dataframe for inspection.
    """
    if not labeled_swings:
        return pd.DataFrame(
            columns=["ts", "price", "type", "index", "strength", "rel_label"]
        )

    data = [
        {
            "ts": s.ts,
            "price": s.price,
            "type": s.type.value,
            "index": s.index,
            "strength": s.strength,
            "rel_label": s.rel_label,
        }
        for s in labeled_swings
    ]
    df = pd.DataFrame(data).set_index("ts").sort_index()
    return df
