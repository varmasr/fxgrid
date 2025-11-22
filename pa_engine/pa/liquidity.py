# pa_engine/pa/liquidity.py

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence, Tuple

import pandas as pd

from pa_engine.pa.structure import LabeledSwingPoint


class LiquidityType(str, Enum):
    EQUAL_HIGH = "EQUAL_HIGH"
    EQUAL_LOW = "EQUAL_LOW"
    ASIA_HIGH = "ASIA_HIGH"
    ASIA_LOW = "ASIA_LOW"


class SweepSide(str, Enum):
    BUY_SIDE = "BUY_SIDE"   # liquidity above price (sweeps of highs)
    SELL_SIDE = "SELL_SIDE" # liquidity below price (sweeps of lows)


@dataclass
class LiquidityLevel:
    """
    Represents a price area where liquidity is expected:
      - cluster of equal highs / equal lows
      - Asia session high / low
    """
    ts: pd.Timestamp          # reference timestamp (e.g., last touch)
    price: float
    type: LiquidityType
    touches: int              # how many swing points formed this level
    swing_indices: List[int]  # indices of contributing swing points


@dataclass
class LiquiditySweep:
    """
    Represents a sweep through a liquidity level:
      - e.g., wick above equal highs then close back below.
    """
    ts: pd.Timestamp          # timestamp of the sweep candle
    level: LiquidityLevel
    side: SweepSide           # BUY_SIDE (taking out highs) or SELL_SIDE (taking out lows)
    close_back_in_range: bool # did candle close back through the level?
    high: float
    low: float
    close: float
    score: float = 0.0



# ----------------------------------------------------------------------
# 1) Equal High/Low Liquidity from swings
# ----------------------------------------------------------------------

def detect_equal_highs_lows(
    swings: Sequence[LabeledSwingPoint],
    tolerance_abs: float,
    min_touches: int = 2,
) -> List[LiquidityLevel]:
    """
    Detect clusters of equal highs / equal lows among labeled swings.

    We form simple clusters where swing prices are within tolerance_abs
    of the cluster center. Clusters with >= min_touches become LiquidityLevels.
    """
    if not swings:
        return []

    # Separate highs and lows
    high_swings: List[LabeledSwingPoint] = [s for s in swings if s.type.value == "HIGH"]
    low_swings: List[LabeledSwingPoint] = [s for s in swings if s.type.value == "LOW"]

    levels: List[LiquidityLevel] = []

    def _cluster_swings(
        sws: List[LabeledSwingPoint],
        liq_type: LiquidityType,
    ) -> None:
        # Sort by price to cluster easily
        sws_sorted = sorted(sws, key=lambda s: float(s.price))
        current_cluster: List[LabeledSwingPoint] = []

        def flush_cluster():
            nonlocal levels, current_cluster, liq_type
            if len(current_cluster) >= min_touches:
                prices = [float(s.price) for s in current_cluster]
                # Use average as cluster price
                lvl_price = sum(prices) / len(prices)
                # Use last swing ts as reference
                last_s = current_cluster[-1]
                levels.append(
                    LiquidityLevel(
                        ts=last_s.ts,
                        price=lvl_price,
                        type=liq_type,
                        touches=len(current_cluster),
                        swing_indices=[s.index for s in current_cluster],
                    )
                )
            current_cluster = []

        for s in sws_sorted:
            if not current_cluster:
                current_cluster = [s]
            else:
                center_price = float(current_cluster[0].price)
                if abs(float(s.price) - center_price) <= tolerance_abs:
                    current_cluster.append(s)
                else:
                    flush_cluster()
                    current_cluster = [s]

        flush_cluster()

    _cluster_swings(high_swings, LiquidityType.EQUAL_HIGH)
    _cluster_swings(low_swings, LiquidityType.EQUAL_LOW)

    return levels


# ----------------------------------------------------------------------
# 2) Asia session range liquidity
# ----------------------------------------------------------------------

def detect_asia_range_liquidity(
    df_m1: pd.DataFrame,
    session_col: str = "session",
    asia_label: str = "ASIA",
) -> List[LiquidityLevel]:
    """
    Detect Asia session high/low as liquidity levels.
    Assumes df_m1 is M1 data for (at most) a couple of days and has a
    'session' column (from infer_session).

    We take the latest calendar date in df_m1 and restrict to that date
    where session == asia_label.
    """
    if df_m1.empty or session_col not in df_m1.columns:
        return []

    df = df_m1.copy().sort_index()
    dates = df.index.date
    unique_dates = sorted(set(dates))
    if not unique_dates:
        return []

    curr_day = unique_dates[-1]
    df_curr = df[df.index.date == curr_day]
    if df_curr.empty:
        return []

    df_asia = df_curr[df_curr[session_col] == asia_label]
    if df_asia.empty:
        return []

    # High and low of the Asia session for that day
    asia_high_price = float(df_asia["high"].max())
    asia_low_price = float(df_asia["low"].min())

    # Use first and last timestamps as references
    ts_high = df_asia["high"].idxmax()
    ts_low = df_asia["low"].idxmin()

    levels: List[LiquidityLevel] = [
        LiquidityLevel(
            ts=ts_high,
            price=asia_high_price,
            type=LiquidityType.ASIA_HIGH,
            touches=1,
            swing_indices=[],
        ),
        LiquidityLevel(
            ts=ts_low,
            price=asia_low_price,
            type=LiquidityType.ASIA_LOW,
            touches=1,
            swing_indices=[],
        ),
    ]

    return levels


# ----------------------------------------------------------------------
# 3) Sweeps of liquidity levels
# ----------------------------------------------------------------------

def detect_sweeps_of_levels(
    df: pd.DataFrame,
    levels: Sequence[LiquidityLevel],
    lookback_bars: int = 200,
) -> List[LiquiditySweep]:
    """
    Detect basic liquidity sweeps over the given levels.

    Rules:
      - For each level, search the last `lookback_bars` candles.
      - BUY_SIDE sweep (taking highs):
          high > level.price AND close < level.price
      - SELL_SIDE sweep (taking lows):
          low < level.price AND close > level.price
      - close_back_in_range is True when close crosses back over the level.

    This is intentionally simple; we can refine it later (multi-bar sweeps, etc.).
    """
    if df.empty or not levels:
        return []

    df = df.copy().sort_index()
    df_tail = df.tail(lookback_bars)

    sweeps: List[LiquiditySweep] = []

    for lvl in levels:
        price = lvl.price

        for ts, row in df_tail.iterrows():
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])

            # Sweep of highs: price trades above level, but close back below
            if high > price and close < price:
                sweeps.append(
                    LiquiditySweep(
                        ts=ts,
                        level=lvl,
                        side=SweepSide.BUY_SIDE,
                        close_back_in_range=True,
                        high=high,
                        low=low,
                        close=close,
                    )
                )

            # Sweep of lows: price trades below level, but close back above
            if low < price and close > price:
                sw = LiquiditySweep(
                    ts=ts,
                    level=lvl,
                    side=SweepSide.SELL_SIDE,
                    close_back_in_range=True,
                    high=high,
                    low=low,
                    close=close,
                )
                sw.score = score_sweep(df, sw)
                sweeps.append(sw)


    return sweeps


def score_sweep(
    df: pd.DataFrame,
    sweep: LiquiditySweep,
    lookahead_bars: int = 3,
) -> float:
    """
    Score a sweep 0–100 based on:
        - penetration depth
        - reclaim strength
        - displacement after sweep

    Inputs:
       df            : M1 or M5 dataframe (must contain 'high','low','close')
       sweep         : LiquiditySweep instance
       lookahead_bars: candles to measure displacement

    Returns:
       float score between 0 and 100.
    """
    lvl = sweep.level
    price = lvl.price
    ts = sweep.ts

    # -----------------------
    # 1. PENETRATION DEPTH
    # -----------------------
    if sweep.side == SweepSide.SELL_SIDE:
        # wick went below level
        penetration = price - sweep.low
    else:
        # BUY_SIDE : wick above level
        penetration = sweep.high - price

    penetration = max(penetration, 0)
    # normalize penetration vs ATR(14) if available, else price scale
    if "atr_14" in df.columns:
        atr = float(df.loc[ts, "atr_14"])
        depth_score = min(100.0, (penetration / (0.5 * atr)) * 100.0)
    else:
        depth_score = min(100.0, (penetration / (0.0005)) * 100.0)

    # -----------------------
    # 2. RECLAIM STRENGTH
    # -----------------------
    # distance between close and level, relative to range
    candle_range = sweep.high - sweep.low
    if candle_range > 0:
        reclaim_rel = abs(sweep.close - price) / candle_range
    else:
        reclaim_rel = 0

    reclaim_score = min(100.0, reclaim_rel * 100.0)

    # -----------------------
    # 3. DISPLACEMENT AFTER SWEEP
    # -----------------------
    df_after = df[df.index > ts].head(lookahead_bars)

    if df_after.empty:
        displacement_score = 0.0
    else:
        if sweep.side == SweepSide.SELL_SIDE:
            # look for upward displacement
            disp = df_after["close"].iloc[-1] - sweep.close
        else:
            # BUY_SIDE sweep → displacement downward
            disp = sweep.close - df_after["close"].iloc[-1]

        # normalize displacement using ATR
        if "atr_14" in df.columns:
            atr = float(df.loc[ts, "atr_14"])
            displacement_score = min(100.0, (disp / (0.5 * atr)) * 100.0)
        else:
            displacement_score = min(100.0, (disp / 0.0005) * 100.0)
        displacement_score = max(0.0, displacement_score)

    # -----------------------
    # Weighted Total
    # -----------------------
    total = (
        0.35 * depth_score +
        0.35 * reclaim_score +
        0.30 * displacement_score
    )
    return round(total, 2)
