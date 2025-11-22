# pa_engine/pa/strategy_context.py

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from pa_engine.pa.context_bkp import PAContext, TimeframePAContext
from pa_engine.pa.trend import TrendStateEnum
from pa_engine.pa.order_blocks import OrderBlock
from pa_engine.pa.fvg import FairValueGap
from pa_engine.pa.liquidity import LiquidityLevel, LiquiditySweep, LiquidityType, SweepSide


@dataclass
class StrategyContext:
    """
    A compact, strategy-ready view of PAContext.

    This is what:
      - strategies will consume
      - backtests will log
      - LLM commentary will read
    """
    instrument: str
    base_tf: str
    asof_utc: datetime

    price: float
    session: str

    htf_tf: str
    htf_trend: TrendStateEnum
    stf_trend: TrendStateEnum
    bias: str  # "BUY", "SELL", "NEUTRAL"

    daily_levels: Dict[str, Any] = field(default_factory=dict)
    session_levels: Dict[str, Any] = field(default_factory=dict)

    active_ob: Optional[OrderBlock] = None
    active_fvg: Optional[FairValueGap] = None

    asia_range: Optional[Dict[str, float]] = None

    liquidity_levels: List[LiquidityLevel] = field(default_factory=list)
    liquidity_sweeps: List[LiquiditySweep] = field(default_factory=list)

    notes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to a JSON-serializable dict for logging / LLM prompts.
        (We avoid serializing full OHLC history here.)
        """
        d = asdict(self)

        # Convert enums to values
        d["htf_trend"] = self.htf_trend.value if self.htf_trend else None
        d["stf_trend"] = self.stf_trend.value if self.stf_trend else None

        # Sanitize LiquidityLevel / LiquiditySweep lists
        def _simplify_level(lvl: LiquidityLevel) -> Dict[str, Any]:
            return {
                "ts": lvl.ts.isoformat(),
                "price": lvl.price,
                "type": lvl.type.value,
                "touches": lvl.touches,
            }

        def _simplify_sweep(sw: LiquiditySweep) -> Dict[str, Any]:
            return {
                "ts": sw.ts.isoformat(),
                "level_type": sw.level.type.value,
                "level_price": sw.level.price,
                "side": sw.side.value,
                "score": getattr(sw, "score", None),
                "high": sw.high,
                "low": sw.low,
                "close": sw.close,
            }

        d["liquidity_levels"] = [_simplify_level(l) for l in self.liquidity_levels]
        d["liquidity_sweeps"] = [_simplify_sweep(s) for s in self.liquidity_sweeps]

        # Strip heavy objects from OB and FVG
        if self.active_ob is not None:
            d["active_ob"] = {
                "ts": self.active_ob.ts.isoformat(),
                "type": self.active_ob.type,
                "low": self.active_ob.low,
                "high": self.active_ob.high,
                "score": getattr(self.active_ob, "score", None),
            }
        if self.active_fvg is not None:
            d["active_fvg"] = {
                "ts_start": self.active_fvg.ts_start.isoformat(),
                "ts_end": self.active_fvg.ts_end.isoformat(),
                "direction": self.active_fvg.direction,
                "gap_low": self.active_fvg.gap_low,
                "gap_high": self.active_fvg.gap_high,
                "size_abs": self.active_fvg.size_abs,
                "size_atr": self.active_fvg.size_atr,
                "is_filled": self.active_fvg.is_filled,
            }

        return d


from pa_engine.pa.context import PAContext, TimeframePAContext

def _pick_tf(pa_ctx: PAContext, tf: str) -> TimeframePAContext:
    """
    Pick timeframe context from PAContext using tf_contexts (M1, M5, M15, H1).
    """
    if tf not in pa_ctx.tf_contexts:
        raise ValueError(f"Timeframe {tf} not in pa_ctx.tf_contexts (available: {list(pa_ctx.tf_contexts.keys())})")
    return pa_ctx.tf_contexts[tf]



def _infer_bias(htf_trend: TrendStateEnum, stf_trend: TrendStateEnum) -> str:
    """
    Basic bias logic: prefer HTF if aligned with STF.
    """
    if htf_trend == stf_trend and htf_trend in (TrendStateEnum.UP, TrendStateEnum.DOWN):
        return "BUY" if htf_trend == TrendStateEnum.UP else "SELL"

    if stf_trend in (TrendStateEnum.UP, TrendStateEnum.DOWN):
        return "BUY" if stf_trend == TrendStateEnum.UP else "SELL"

    return "NEUTRAL"


def _pick_active_ob(
    tf_ctx: TimeframePAContext,
    price: float,
    bias: str,
) -> Optional[OrderBlock]:
    """
    Choose the most relevant OB based on bias and distance to current price.
    """
    obs = tf_ctx.order_blocks or []
    if not obs:
        return None

    # Simple distance-based selection; we can refine this later.
    if bias == "BUY":
        cands = [ob for ob in obs if ob.type == "DEMAND"]
    elif bias == "SELL":
        cands = [ob for ob in obs if ob.type == "SUPPLY"]
    else:
        cands = obs

    if not cands:
        cands = obs

    def _dist(ob: OrderBlock) -> float:
        mid = (ob.low + ob.high) / 2.0
        return abs(mid - price)

    return sorted(cands, key=_dist)[0]


def _pick_active_fvg(
    tf_ctx: TimeframePAContext,
    price: float,
    bias: str,
) -> Optional[FairValueGap]:
    """
    Choose the closest FVG in the direction of bias.
    """
    fvgs = tf_ctx.fvg_list or []
    if not fvgs:
        return None

    def _fvg_mid(fvg: FairValueGap) -> float:
        return (fvg.gap_low + fvg.gap_high) / 2.0

    if bias == "BUY":
        cands = [f for f in fvgs if _fvg_mid(f) <= price]
    elif bias == "SELL":
        cands = [f for f in fvgs if _fvg_mid(f) >= price]
    else:
        cands = fvgs

    if not cands:
        cands = fvgs

    return sorted(cands, key=lambda f: abs(_fvg_mid(f) - price))[0]


def _extract_asia_range_from_liquidity(levels: List[LiquidityLevel]) -> Optional[Dict[str, float]]:
    asia_high = None
    asia_low = None
    for lvl in levels:
        if lvl.type == LiquidityType.ASIA_HIGH:
            asia_high = lvl.price
        elif lvl.type == LiquidityType.ASIA_LOW:
            asia_low = lvl.price

    if asia_high is None and asia_low is None:
        return None

    return {
        "asia_high": asia_high,
        "asia_low": asia_low,
    }


def _top_liquidity_sweeps(
    sweeps: List[LiquiditySweep],
    min_score: float = 40.0,
    max_items: int = 5,
) -> List[LiquiditySweep]:
    scored = [s for s in sweeps if getattr(s, "score", 0.0) >= min_score]
    scored_sorted = sorted(scored, key=lambda s: getattr(s, "score", 0.0), reverse=True)
    return scored_sorted[:max_items]


def build_strategy_context(
    pa_ctx: PAContext,
    instrument: str,
    base_tf: str = "M5",
    htf_tf: str = "M15",
) -> StrategyContext:
    """
    Build a StrategyContext from a PAContext across multiple timeframes.
    """
    tf_ctx = _pick_tf(pa_ctx, base_tf)
    htf_ctx = pa_ctx.tf_contexts.get(htf_tf, tf_ctx)


    df_tf = tf_ctx.df
    if df_tf.empty:
        raise ValueError(f"No data in timeframe {base_tf} for instrument {instrument}")

    asof_utc = df_tf.index.max()
    price = float(df_tf["close"].iloc[-1])
    session = df_tf["session"].iloc[-1] if "session" in df_tf.columns else "UNKNOWN"

    htf_trend = htf_ctx.trend.state
    stf_trend = tf_ctx.trend.state
    bias = _infer_bias(htf_trend, stf_trend)

    # Daily + session levels already computed in PAContext
    daily_levels = pa_ctx.daily_levels
    session_levels = pa_ctx.session_levels

    # OB/FVG selection
    active_ob = _pick_active_ob(tf_ctx, price, bias)
    active_fvg = _pick_active_fvg(tf_ctx, price, bias)

    # Liquidity levels / sweeps from chosen TF
    liq_levels = tf_ctx.liquidity_levels or []
    liq_sweeps_all = tf_ctx.liquidity_sweeps or []
    liq_sweeps = _top_liquidity_sweeps(liq_sweeps_all)

    asia_range = _extract_asia_range_from_liquidity(liq_levels)

    ctx = StrategyContext(
        instrument=instrument,
        base_tf=base_tf,
        asof_utc=asof_utc,
        price=price,
        session=session,
        htf_tf=htf_tf,
        htf_trend=htf_trend,
        stf_trend=stf_trend,
        bias=bias,
        daily_levels=daily_levels,
        session_levels=session_levels,
        active_ob=active_ob,
        active_fvg=active_fvg,
        asia_range=asia_range,
        liquidity_levels=liq_levels,
        liquidity_sweeps=liq_sweeps,
        notes={},
    )

    return ctx
