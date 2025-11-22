# pa_engine/pa/context.py
# FINAL VERSION – aligned with your old working version + new engines
# (OB/FVG/Liquidity/Sweeps/Trend/Features all integrated)
# Compatible with debug_pa_context, StrategyContext, LLM Commentary

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

import pandas as pd

# DB
from pa_engine.db.candles import load_m1_candles
from pa_engine.db.resampler import resample_tf

# Feature engines
from pa_engine.pa.features import (
    FeatureConfig,
    add_core_features,
    compute_daily_levels,
    compute_session_levels,
)

# Structure / Trend
from pa_engine.pa.structure import (
    detect_swings,
    label_swings,
    LabeledSwingPoint,
)
from pa_engine.pa.trend import TrendState, infer_trend_state

# Order Blocks
from pa_engine.pa.order_blocks import (
    detect_order_blocks,
    score_order_blocks,
    OrderBlock,
)

# FVG
from pa_engine.pa.fvg import (
    FairValueGap,
    detect_fvgs,
)

# Liquidity
from pa_engine.pa.liquidity import (
    LiquidityLevel,
    LiquiditySweep,
    detect_equal_highs_lows,
    detect_asia_range_liquidity,
    detect_sweeps_of_levels,
)


# =============================================================
# Data structures
# =============================================================

@dataclass
class TimeframePAContext:
    tf: str
    df: pd.DataFrame

    swings: List[LabeledSwingPoint]
    trend: TrendState

    order_blocks: List[OrderBlock]
    fvg_list: List[FairValueGap]

    liquidity_levels: List[LiquidityLevel]
    liquidity_sweeps: List[LiquiditySweep]


@dataclass
class PAContext:
    """
    Full multi-timeframe PA context for one instrument.

    NOTE: This matches your OLD working structure:
        - base_tf
        - tfs list
        - tf_contexts dict
    """
    instrument: str
    asof_utc: datetime

    base_tf: str
    tfs: List[str]

    tf_contexts: Dict[str, TimeframePAContext]

    daily_levels: dict
    session_levels: dict


# =============================================================
# Internal builder for a single TF
# =============================================================

def _build_single_tf_context(
    tf: str,
    df_tf: pd.DataFrame,
    feature_cfg: FeatureConfig,
    is_m1: bool = False,
) -> TimeframePAContext:
    """
    Build PA context for a single timeframe.
    """
    if df_tf.empty:
        return TimeframePAContext(
            tf=tf,
            df=df_tf,
            swings=[],
            trend=TrendState(state=None, reason="EMPTY_DF", tf=tf),
            order_blocks=[],
            fvg_list=[],
            liquidity_levels=[],
            liquidity_sweeps=[],
        )

    # 1. swings
    swings = label_swings(detect_swings(df_tf, left=2, right=2))

    # 2. trend
    trend = infer_trend_state(df_tf, swings, ema_col="ema_50", tf=tf)

    # 3. Order Blocks + scoring
    raw_obs = detect_order_blocks(df_tf, swings, tf=tf)
    scored_obs = score_order_blocks(df_tf, raw_obs, trend=trend, atr_col="atr_14")

    # 4. Fair Value Gaps
    fvgs = detect_fvgs(
        df_tf,
        tf=tf,
        atr_col="atr_14",
        min_size_frac_atr=0.0,
    )

    # 5. Liquidity levels (equal highs/lows)
    liq_swings = detect_equal_highs_lows(
        swings=swings,
        tolerance_abs=0.0005,
        min_touches=2,
    )

    # 6. Asia range (M1 only)
    liq_asia = detect_asia_range_liquidity(df_tf) if is_m1 else []

    all_liq = liq_swings + liq_asia

    # 7. Sweeps of liquidity
    sweeps = detect_sweeps_of_levels(df_tf, all_liq, lookback_bars=200)

    return TimeframePAContext(
        tf=tf,
        df=df_tf,
        swings=swings,
        trend=trend,
        order_blocks=scored_obs,
        fvg_list=fvgs,
        liquidity_levels=all_liq,
        liquidity_sweeps=sweeps,
    )


# =============================================================
# Build multi-timeframe context from M1
# =============================================================

def build_pa_context_from_m1(
    instrument: str,
    df_m1: pd.DataFrame,
    tfs: Sequence[str] = ("M1", "M5", "M15", "H1"),
    feature_cfg: Optional[FeatureConfig] = None,
) -> PAContext:

    if feature_cfg is None:
        feature_cfg = FeatureConfig(
            atr_period=14,
            ema_periods=(20, 50),
            donchian_periods=(20, 50),
        )

    if df_m1.empty:
        now_utc = datetime.now(timezone.utc)
        return PAContext(
            instrument=instrument,
            asof_utc=now_utc,
            base_tf="M1",
            tfs=list(tfs),
            tf_contexts={},
            daily_levels={},
            session_levels={},
        )

    df_m1 = df_m1.sort_index()

    # === Daily + Session Levels ===
    daily_levels = compute_daily_levels(df_m1)
    session_levels = compute_session_levels(df_m1)

    # === Core M1 features ===
    df_m1_feat = add_core_features(df_m1, feature_cfg)

    tf_contexts: Dict[str, TimeframePAContext] = {}

    for tf in tfs:
        if tf == "M1":
            df_tf = df_m1_feat
            tf_ctx = _build_single_tf_context(tf, df_tf, feature_cfg, is_m1=True)
        else:
            df_tf_raw = resample_tf(df_m1_feat, tf)
            df_tf = add_core_features(df_tf_raw, feature_cfg)
            tf_ctx = _build_single_tf_context(tf, df_tf, feature_cfg, is_m1=False)

        tf_contexts[tf] = tf_ctx

    asof_utc = df_m1.index.max().to_pydatetime()

    return PAContext(
        instrument=instrument,
        asof_utc=asof_utc,
        base_tf="M1",
        tfs=list(tfs),
        tf_contexts=tf_contexts,
        daily_levels=daily_levels,
        session_levels=session_levels,
    )


# =============================================================
# Load candles from DB and build PAContext
# =============================================================

def build_pa_context_for_instrument(
    instrument: str,
    hours_back: int = 24,
    tfs: Sequence[str] = ("M1", "M5", "M15", "H1"),
    feature_cfg: Optional[FeatureConfig] = None,
) -> PAContext:

    end = datetime.now(timezone.utc)
    start = end - pd.Timedelta(hours=hours_back)

    df_m1 = load_m1_candles(instrument, start, end)

    return build_pa_context_from_m1(
        instrument=instrument,
        df_m1=df_m1,
        tfs=tfs,
        feature_cfg=feature_cfg,
    )


# =============================================================
# Compact dict for LLM commentary + debug
# =============================================================

def pa_context_to_dict(ctx: PAContext) -> dict:
    """
    Convert PAContext to JSON-safe dict.  
    Compatible with debug_pa_context & LLM commentary engine.
    """
    out = {
        "instrument": ctx.instrument,
        "asof_utc": ctx.asof_utc.isoformat(),
        "base_tf": ctx.base_tf,
        "tfs": ctx.tfs,
        "daily_levels": ctx.daily_levels,
        "session_levels": ctx.session_levels,
        "tfs_detail": {},
    }

    for tf, tf_ctx in ctx.tf_contexts.items():

        swings_summary = []
        for s in tf_ctx.swings[-10:]:
            swings_summary.append({
                "ts": s.ts.isoformat(),
                "price": float(s.price),
                "type": s.type.value,
                "rel_label": s.rel_label,
            })

        obs_sorted = sorted(
            tf_ctx.order_blocks,
            key=lambda ob: (ob.score or 0.0),
            reverse=True,
        )

        ob_summary = []
        for ob in obs_sorted[:5]:
            ob_summary.append({
                "ts": ob.ts.isoformat(),
                "type": ob.type.value,
                "low": ob.low,
                "high": ob.high,
                "body_low": ob.body_low,
                "body_high": ob.body_high,
                "score": ob.score,
            })

        fvg_summary = [
            {
                "ts_start": f.ts_start.isoformat(),
                "ts_end": f.ts_end.isoformat(),
                "direction": f.direction.value,
                "gap_low": f.gap_low,
                "gap_high": f.gap_high,
                "is_filled": f.is_filled,
            }
            for f in tf_ctx.fvg_list[-10:]
        ]

        out["tfs_detail"][tf] = {
            "swings": swings_summary,
            "trend": {
                "state": tf_ctx.trend.state.value if tf_ctx.trend.state else None,
                "reason": tf_ctx.trend.reason,
            },
            "order_blocks": ob_summary,
            "fvg": fvg_summary,
        }

    return out
