# pa_engine/pa/trend.py

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import pandas as pd

from pa_engine.pa.structure import LabeledSwingPoint, SwingType


class TrendStateEnum(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    RANGE = "RANGE"
    UNCLEAR = "UNCLEAR"


@dataclass
class TrendState:
    state: TrendStateEnum
    reason: str
    tf: Optional[str] = None  # e.g. 'M15','H1'


def infer_trend_state(
    df: pd.DataFrame,
    swings: List[LabeledSwingPoint],
    ema_col: str = "ema_50",
    min_swings: int = 4,
    tf: Optional[str] = None,
) -> TrendState:
    """
    Infer trend based on swing labels + EMA position.

    Heuristics:
      - UP if:
          * recent swing highs mostly HH
          * recent swing lows mostly HL
          * close > EMA
      - DOWN if:
          * recent swing highs mostly LH
          * recent swing lows mostly LL
          * close < EMA
      - RANGE otherwise, if at least some structure exists.
      - UNCLEAR if we don't even have enough swings.
    """
    if df.empty or len(swings) < min_swings:
        return TrendState(
            state=TrendStateEnum.UNCLEAR,
            reason="Not enough data or swings to determine trend.",
            tf=tf,
        )

    if ema_col not in df.columns:
        return TrendState(
            state=TrendStateEnum.UNCLEAR,
            reason=f"EMA column '{ema_col}' not present.",
            tf=tf,
        )

    # Use latest close vs EMA as directional confirmation
    last_row = df.iloc[-1]
    last_close = float(last_row["close"])
    last_ema = float(last_row[ema_col])

    # Consider only last N swings
    recent_swings = swings[-min_swings:]

    highs = [s for s in recent_swings if s.type == SwingType.HIGH and s.rel_label]
    lows = [s for s in recent_swings if s.type == SwingType.LOW and s.rel_label]

    high_labels = [s.rel_label for s in highs]
    low_labels = [s.rel_label for s in lows]

    # Count patterns
    hh_count = high_labels.count("HH")
    lh_count = high_labels.count("LH")
    hl_count = low_labels.count("HL")
    ll_count = low_labels.count("LL")

    # Simple heuristics:
    up_structure = hh_count >= lh_count and hl_count >= ll_count and (hh_count + hl_count) > 0
    down_structure = lh_count >= hh_count and ll_count >= hl_count and (lh_count + ll_count) > 0

    close_above_ema = last_close > last_ema
    close_below_ema = last_close < last_ema

    # Decide:
    if up_structure and close_above_ema:
        reason = (
            f"UP: highs={high_labels}, lows={low_labels}, "
            f"close({last_close:.3f}) > {ema_col}({last_ema:.3f})"
        )
        return TrendState(state=TrendStateEnum.UP, reason=reason, tf=tf)

    if down_structure and close_below_ema:
        reason = (
            f"DOWN: highs={high_labels}, lows={low_labels}, "
            f"close({last_close:.3f}) < {ema_col}({last_ema:.3f})"
        )
        return TrendState(state=TrendStateEnum.DOWN, reason=reason, tf=tf)

    # If we have some structure but no clear direction
    if highs or lows:
        reason = (
            f"RANGE: highs={high_labels}, lows={low_labels}, "
            f"close={last_close:.3f}, {ema_col}={last_ema:.3f}"
        )
        return TrendState(state=TrendStateEnum.RANGE, reason=reason, tf=tf)

    # Fallback
    return TrendState(
        state=TrendStateEnum.UNCLEAR,
        reason="Structure insufficient to determine clear trend.",
        tf=tf,
    )
