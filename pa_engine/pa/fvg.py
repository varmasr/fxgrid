# pa_engine/pa/fvg.py

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence

import pandas as pd


class FVGDirection(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"


@dataclass
class FairValueGap:
    """
    Fair Value Gap (FVG) detected on a given timeframe.

    We use a 3-candle definition:

      Bullish FVG: low[i+2] > high[i]
          gap_low  = high[i]
          gap_high = low[i+2]

      Bearish FVG: high[i+2] < low[i]
          gap_low  = high[i+2]
          gap_high = low[i]
    """
    tf: Optional[str]             # e.g. 'M15', 'H1'
    direction: FVGDirection

    idx_start: int                # index of first candle in pattern (i)
    idx_mid: int                  # i+1
    idx_end: int                  # i+2

    ts_start: pd.Timestamp
    ts_end: pd.Timestamp

    gap_low: float                # lower bound of gap
    gap_high: float               # upper bound of gap

    size_abs: float               # gap_high - gap_low
    size_atr: Optional[float] = None  # gap size in ATR multiples (if ATR available)

    is_filled: bool = False
    filled_ts: Optional[pd.Timestamp] = None


def _get_atr_value(df: pd.DataFrame, idx: int, atr_col: str) -> Optional[float]:
    if atr_col in df.columns:
        try:
            return float(df[atr_col].iloc[idx])
        except Exception:
            return None
    # Fallback: average last 20 ranges
    if {"high", "low"} <= set(df.columns):
        ranges = df["high"] - df["low"]
        if not ranges.empty:
            return float(ranges.tail(20).mean())
    return None


def detect_fvgs(
    df: pd.DataFrame,
    tf: Optional[str] = None,
    atr_col: str = "atr_14",
    min_size_frac_atr: float = 0.1,
) -> List[FairValueGap]:
    """
    Detect Fair Value Gaps on a timeframe dataframe.

    Args:
        df: dataframe with columns 'open','high','low','close'
        tf: timeframe label (e.g. 'M15')
        atr_col: name of ATR column to normalize gap size
        min_size_frac_atr: minimum gap size in ATR multiples.
                           If 0, keep all gaps regardless of size.

    Returns:
        List of FairValueGap instances, with is_filled/fill_ts populated.
    """
    fvgs: List[FairValueGap] = []

    if df.empty or len(df) < 3:
        return fvgs

    highs = df["high"]
    lows = df["low"]
    idx = df.index

    n = len(df)

    for i in range(0, n - 2):
        hi0 = float(highs.iloc[i])
        lo0 = float(lows.iloc[i])
        hi2 = float(highs.iloc[i + 2])
        lo2 = float(lows.iloc[i + 2])

        # Bullish FVG
        if lo2 > hi0:
            gap_low = hi0
            gap_high = lo2
            size_abs = gap_high - gap_low
            atr_val = _get_atr_value(df, i + 1, atr_col)
            size_atr = (size_abs / atr_val) if atr_val and atr_val > 0 else None

            # Filter by size in ATR multiples
            if min_size_frac_atr > 0.0 and size_atr is not None:
                if size_atr < min_size_frac_atr:
                    continue

            fvgs.append(
                FairValueGap(
                    tf=tf,
                    direction=FVGDirection.BULLISH,
                    idx_start=i,
                    idx_mid=i + 1,
                    idx_end=i + 2,
                    ts_start=idx[i],
                    ts_end=idx[i + 2],
                    gap_low=gap_low,
                    gap_high=gap_high,
                    size_abs=size_abs,
                    size_atr=size_atr,
                )
            )

        # Bearish FVG
        if hi2 < lo0:
            gap_low = hi2
            gap_high = lo0
            size_abs = gap_high - gap_low
            atr_val = _get_atr_value(df, i + 1, atr_col)
            size_atr = (size_abs / atr_val) if atr_val and atr_val > 0 else None

            if min_size_frac_atr > 0.0 and size_atr is not None:
                if size_atr < min_size_frac_atr:
                    continue

            fvgs.append(
                FairValueGap(
                    tf=tf,
                    direction=FVGDirection.BEARISH,
                    idx_start=i,
                    idx_mid=i + 1,
                    idx_end=i + 2,
                    ts_start=idx[i],
                    ts_end=idx[i + 2],
                    gap_low=gap_low,
                    gap_high=gap_high,
                    size_abs=size_abs,
                    size_atr=size_atr,
                )
            )

    # After collecting all, compute fill status using the full df
    _mark_fvg_fills(df, fvgs)

    return fvgs


def _mark_fvg_fills(df: pd.DataFrame, fvgs: Sequence[FairValueGap]) -> None:
    """
    For each FVG, determine if/when it gets filled.

    Simple rule:
      - Bullish FVG: filled when any later candle has low <= gap_low
      - Bearish FVG: filled when any later candle has high >= gap_high
    """
    if df.empty:
        return

    highs = df["high"]
    lows = df["low"]
    idx = df.index
    n = len(df)

    for fvg in fvgs:
        start_j = fvg.idx_end + 1
        if start_j >= n:
            continue

        filled_ts: Optional[pd.Timestamp] = None

        if fvg.direction == FVGDirection.BULLISH:
            for j in range(start_j, n):
                if float(lows.iloc[j]) <= fvg.gap_low:
                    filled_ts = idx[j]
                    break
        else:  # BEARISH
            for j in range(start_j, n):
                if float(highs.iloc[j]) >= fvg.gap_high:
                    filled_ts = idx[j]
                    break

        if filled_ts is not None:
            fvg.is_filled = True
            fvg.filled_ts = filled_ts


def fvgs_to_dataframe(fvgs: Sequence[FairValueGap]) -> pd.DataFrame:
    """
    Helper: convert FVG list to dataframe for debugging/inspection.
    """
    if not fvgs:
        return pd.DataFrame(
            columns=[
                "ts_start",
                "ts_end",
                "tf",
                "direction",
                "gap_low",
                "gap_high",
                "size_abs",
                "size_atr",
                "is_filled",
                "filled_ts",
            ]
        )

    data = []
    for f in fvgs:
        data.append(
            {
                "ts_start": f.ts_start,
                "ts_end": f.ts_end,
                "tf": f.tf,
                "direction": f.direction.value,
                "gap_low": f.gap_low,
                "gap_high": f.gap_high,
                "size_abs": f.size_abs,
                "size_atr": f.size_atr,
                "is_filled": f.is_filled,
                "filled_ts": f.filled_ts,
            }
        )

    df = pd.DataFrame(data).set_index("ts_start").sort_index()
    return df
