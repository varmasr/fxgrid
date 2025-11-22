# pa_engine/pa/order_blocks.py

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import pandas as pd

from pa_engine.pa.structure import LabeledSwingPoint, SwingType


class BOSType(str, Enum):
    UP = "UP"
    DOWN = "DOWN"


@dataclass
class BreakOfStructure:
    """
    A structural break inferred from swings.

    For now:
      - HIGH swing with rel_label='HH' => UP BOS (break above prior high)
      - LOW  swing with rel_label='LL' => DOWN BOS (break below prior low)
    """
    ts: pd.Timestamp
    idx: int              # integer index in the TF dataframe
    bos_type: BOSType
    broken_level: float   # price of the prior swing that got broken


class OrderBlockType(str, Enum):
    DEMAND = "DEMAND"
    SUPPLY = "SUPPLY"


@dataclass
class OrderBlock:
    """
    Basic Order Block representation.
    """
    tf: Optional[str]          # e.g. 'M15', 'H1'
    type: OrderBlockType

    ts: pd.Timestamp           # time of the OB origin candle
    idx: int                   # index of OB candle in df

    low: float                 # full candle range
    high: float
    body_low: float            # body range
    body_high: float

    bos_ts: pd.Timestamp       # BOS swing time
    bos_idx: int               # BOS swing index in df
    broken_level: float        # swing price that got broken

    is_mitigated: bool = False

    # New fields
    score: Optional[float] = None
    score_components: Optional[dict] = None


# ---------- BOS detection from swings ----------

def detect_bos_from_swings(swings: List[LabeledSwingPoint]) -> List[BreakOfStructure]:
    """
    Convert labeled swings (HH/HL/LH/LL) into BOS events.

    Logic:
      - HIGH with rel_label='HH' => UP BOS (break above previous high)
      - LOW  with rel_label='LL' => DOWN BOS (break below previous low)
    """
    bos_list: List[BreakOfStructure] = []

    # Maintain last swing of each type to know broken level
    last_high: Optional[LabeledSwingPoint] = None
    last_low: Optional[LabeledSwingPoint] = None

    for s in swings:
        if s.type == SwingType.HIGH:
            if last_high is not None and s.rel_label == "HH":
                bos_list.append(
                    BreakOfStructure(
                        ts=s.ts,
                        idx=s.index,
                        bos_type=BOSType.UP,
                        broken_level=float(last_high.price),
                    )
                )
            last_high = s

        elif s.type == SwingType.LOW:
            if last_low is not None and s.rel_label == "LL":
                bos_list.append(
                    BreakOfStructure(
                        ts=s.ts,
                        idx=s.index,
                        bos_type=BOSType.DOWN,
                        broken_level=float(last_low.price),
                    )
                )
            last_low = s

    return bos_list


# ---------- Order Block detection ----------

def detect_order_blocks(
    df: pd.DataFrame,
    swings: List[LabeledSwingPoint],
    tf: Optional[str] = None,
    max_lookback_bars: int = 20,
) -> List[OrderBlock]:
    """
    Detect basic demand/supply order blocks on a given timeframe.

    Args:
        df: candle dataframe with columns: open, high, low, close
            index is datetime, but we rely on integer positions (0..N-1)
        swings: labeled swings for this timeframe
        tf: timeframe label (e.g., 'M15')
        max_lookback_bars: how many candles back from BOS to search for OB origin

    Returns:
        List of OrderBlock instances.
    """
    if df.empty or not swings:
        return []

    bos_list = detect_bos_from_swings(swings)
    if not bos_list:
        return []

    obs: List[OrderBlock] = []

    # We will use positional indexing (iloc) based on swing.index
    n = len(df)

    for bos in bos_list:
        bos_idx = bos.idx
        if bos_idx <= 0 or bos_idx >= n:
            continue

        if bos.bos_type == BOSType.UP:
            # Look for last bearish candle before BOS
            start = max(0, bos_idx - max_lookback_bars)
            ob_idx = None
            for i in range(bos_idx - 1, start - 1, -1):
                row = df.iloc[i]
                if row["close"] < row["open"]:  # bearish
                    ob_idx = i
                    break

            if ob_idx is None:
                continue

            row = df.iloc[ob_idx]
            _low = float(row["low"])
            _high = float(row["high"])
            o = float(row["open"])
            c = float(row["close"])
            body_low = min(o, c)
            body_high = max(o, c)

            obs.append(
                OrderBlock(
                    tf=tf,
                    type=OrderBlockType.DEMAND,
                    ts=df.index[ob_idx],
                    idx=ob_idx,
                    low=_low,
                    high=_high,
                    body_low=body_low,
                    body_high=body_high,
                    bos_ts=bos.ts,
                    bos_idx=bos_idx,
                    broken_level=bos.broken_level,
                )
            )

        elif bos.bos_type == BOSType.DOWN:
            # Look for last bullish candle before BOS
            start = max(0, bos_idx - max_lookback_bars)
            ob_idx = None
            for i in range(bos_idx - 1, start - 1, -1):
                row = df.iloc[i]
                if row["close"] > row["open"]:  # bullish
                    ob_idx = i
                    break

            if ob_idx is None:
                continue

            row = df.iloc[ob_idx]
            _low = float(row["low"])
            _high = float(row["high"])
            o = float(row["open"])
            c = float(row["close"])
            body_low = min(o, c)
            body_high = max(o, c)

            obs.append(
                OrderBlock(
                    tf=tf,
                    type=OrderBlockType.SUPPLY,
                    ts=df.index[ob_idx],
                    idx=ob_idx,
                    low=_low,
                    high=_high,
                    body_low=body_low,
                    body_high=body_high,
                    bos_ts=bos.ts,
                    bos_idx=bos_idx,
                    broken_level=bos.broken_level,
                )
            )

    return obs


def order_blocks_to_dataframe(obs: List[OrderBlock]) -> pd.DataFrame:
    """
    Convert list of OBs to dataframe including scoring.
    """
    if not obs:
        return pd.DataFrame(
            columns=[
                "ts","tf","type",
                "low","high","body_low","body_high",
                "bos_ts","broken_level",
                "is_mitigated",
                "score","score_components",
            ]
        )

    data = []
    for ob in obs:
        data.append(
            {
                "ts": ob.ts,
                "tf": ob.tf,
                "type": ob.type.value,
                "low": ob.low,
                "high": ob.high,
                "body_low": ob.body_low,
                "body_high": ob.body_high,
                "bos_ts": ob.bos_ts,
                "broken_level": ob.broken_level,
                "is_mitigated": ob.is_mitigated,
                "score": ob.score,
                "score_components": ob.score_components,
            }
        )

    df = pd.DataFrame(data).set_index("ts").sort_index()
    return df


from pa_engine.pa.trend import TrendState, TrendStateEnum
from typing import Sequence


def _clip_score(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def score_order_block(
    df: pd.DataFrame,
    ob: OrderBlock,
    trend: Optional[TrendState] = None,
    atr_col: str = "atr_14",
) -> OrderBlock:
    """
    Compute a simple score for a single OrderBlock.

    Factors:
      - Trend alignment
      - Freshness (recency of OB)
      - Distance from current price in ATR multiples
      - Mitigation status
    """
    if df.empty or ob.idx >= len(df):
        ob.score = 0.0
        ob.score_components = {"reason": "OB index out of range or empty df"}
        return ob

    last_row = df.iloc[-1]
    last_close = float(last_row["close"])

    # 1) Trend alignment
    trend_score = 0.0
    trend_state = trend.state if trend is not None else None

    if trend_state == TrendStateEnum.UP and ob.type == OrderBlockType.DEMAND:
        trend_score = 30.0
    elif trend_state == TrendStateEnum.DOWN and ob.type == OrderBlockType.SUPPLY:
        trend_score = 30.0
    elif trend_state in (TrendStateEnum.UP, TrendStateEnum.DOWN):
        # Counter-trend OBs get mild penalty
        trend_score = 5.0
    else:
        # RANGE / UNCLEAR
        trend_score = 10.0  # neutral

    # 2) Freshness: newer OB → higher
    n = len(df)
    age_bars = n - ob.idx  # how many bars since OB candle
    # Anything older than 300 bars gets near zero freshness
    freshness_score = max(0.0, 25.0 * (1.0 - min(age_bars / 300.0, 1.0)))

    # 3) Distance from current price in ATR multiples
    if atr_col in df.columns:
        atr_val = float(last_row[atr_col])
    else:
        # fallback: average candle range as pseudo-ATR
        ranges = df["high"] - df["low"]
        atr_val = float(ranges.tail(50).mean()) if not ranges.empty else 0.0

    distance_score = 0.0
    if atr_val > 0:
        # For DEMAND, look at distance to body_high (top of zone)
        # For SUPPLY, distance to body_low (bottom of zone)
        if ob.type == OrderBlockType.DEMAND:
            ref_price = ob.body_high
        else:
            ref_price = ob.body_low

        dist_atr = abs(last_close - ref_price) / atr_val

        # Ideal zone: roughly 0.5 to 2 ATR away
        if 0.5 <= dist_atr <= 2.0:
            distance_score = 30.0
        elif 0.25 <= dist_atr < 0.5 or 2.0 < dist_atr <= 3.0:
            distance_score = 20.0
        elif 0.1 <= dist_atr < 0.25 or 3.0 < dist_atr <= 4.0:
            distance_score = 10.0
        else:
            distance_score = 0.0

    # 4) Mitigation status
    mitigation_score = 0.0
    if not ob.is_mitigated:
        mitigation_score = 15.0

    total = trend_score + freshness_score + distance_score + mitigation_score
    total = _clip_score(total)

    ob.score = total
    ob.score_components = {
        "trend_score": trend_score,
        "freshness_score": freshness_score,
        "distance_score": distance_score,
        "mitigation_score": mitigation_score,
    }
    return ob


def score_order_blocks(
    df: pd.DataFrame,
    obs: Sequence[OrderBlock],
    trend: Optional[TrendState] = None,
    atr_col: str = "atr_14",
) -> List[OrderBlock]:
    """
    Score a list of OBs and return them (mutated) sorted by descending score.
    """
    scored = [score_order_block(df, ob, trend=trend, atr_col=atr_col) for ob in obs]
    scored.sort(key=lambda o: (o.score or 0.0), reverse=True)
    return scored
