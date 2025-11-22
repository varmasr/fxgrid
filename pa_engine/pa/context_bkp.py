# pa_engine/pa/context.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from pa_engine.db.candles import load_m1_candles
from pa_engine.db.resampler import resample_tf
from pa_engine.pa.features import (
    FeatureConfig,
    add_core_features,
    compute_daily_levels,
    compute_session_levels,
)
from pa_engine.pa.structure import (
    LabeledSwingPoint,
    detect_swings,
    label_swings,
)
from pa_engine.pa.trend import TrendState
from pa_engine.pa.order_blocks import (
    OrderBlock,
    detect_order_blocks,
    score_order_blocks,
)
from pa_engine.pa.fvg import (
    FairValueGap,
    detect_fvgs,
)


# ---------- Dataclasses ----------

# in pa_engine/pa/context.py

from pa_engine.pa.liquidity import (
    LiquidityLevel,
    LiquiditySweep,
    detect_equal_highs_lows,
    detect_asia_range_liquidity,
    detect_sweeps_of_levels,
)

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
    Full multi-timeframe PA context for a single instrument over a given window.
    """
    instrument: str
    asof_utc: datetime

    base_tf: str
    tfs: List[str]
    tf_contexts: Dict[str, TimeframePAContext]

    daily_levels: dict
    session_levels: dict


# ---------- Core builders ----------

def _build_single_tf_context(
    tf: str,
    df_tf: pd.DataFrame,
    feature_cfg: FeatureConfig,
) -> TimeframePAContext:
    """
    Build PA context for a single timeframe dataframe.

    Assumes df_tf already has core features added (EMA, ATR, etc.).
    """
    if df_tf.empty:
        return TimeframePAContext(
            tf=tf,
            df=df_tf,
            swings=[],
            trend=TrendState(state=None, reason="EMPTY_DF", tf=tf),  # type: ignore[arg-type]
            order_blocks=[],
            fvg_list=[],
        )

    # Structure: swings
    swings = label_swings(detect_swings(df_tf, left=2, right=2))

    # Trend
    trend = TrendState(
        state=None,
        reason="UNSET",
        tf=tf,
    )
    try:
        trend = TrendState(
            **infer_trend_state(df_tf, swings, ema_col="ema_50", tf=tf).__dict__
        )  # small defensive wrap if TrendState evolves
    except Exception:
        from pa_engine.pa.trend import infer_trend_state  # local import to avoid cycle

        trend = infer_trend_state(df_tf, swings, ema_col="ema_50", tf=tf)

    # Order Blocks
    raw_obs = detect_order_blocks(df_tf, swings, tf=tf)
    scored_obs = score_order_blocks(df_tf, raw_obs, trend=trend, atr_col="atr_14")

    # FVGs (basic version – fine-tuning later)
    fvgs = detect_fvgs(df_tf, tf=tf, atr_col="atr_14", min_size_frac_atr=0.0)

    # --- Liquidity ---
    # For equal highs/lows we typically use swings from this TF
    # Use a simple tolerance for now: e.g., 0.0005 (for FX) or parameterize later
    liq_levels_swings = detect_equal_highs_lows(
        swings=swings,
        tolerance_abs=0.0005,   # TODO: make configurable per instrument
        min_touches=2,
    )

    # Asia range only makes sense on M1 (or lowest TF)
    liq_levels_asia: List[LiquidityLevel] = []
    if tf == "M1":
        liq_levels_asia = detect_asia_range_liquidity(df_tf)

    all_liq_levels = liq_levels_swings + liq_levels_asia

    liq_sweeps = detect_sweeps_of_levels(df_tf, all_liq_levels, lookback_bars=200)

    return TimeframePAContext(
        tf=tf,
        df=df_tf,
        swings=swings,
        trend=trend,
        order_blocks=scored_obs,
        fvg_list=fvgs,
        liquidity_levels=all_liq_levels,
        liquidity_sweeps=liq_sweeps,
    )


def build_pa_context_from_m1(
    instrument: str,
    df_m1: pd.DataFrame,
    tfs: Sequence[str] = ("M1", "M5", "M15", "H1"),
    feature_cfg: Optional[FeatureConfig] = None,
) -> PAContext:
    """
    Build PAContext given an M1 dataframe for a single instrument.

    Responsibilities:
      - compute daily & session levels from M1
      - build core features on M1
      - resample to higher TFs
      - run PA engines (structure/trend/OB/FVG) per TF
    """
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

    # Ensure proper time index name & type
    df_m1 = df_m1.copy()
    if df_m1.index.name is None:
        df_m1.index.name = "ts_utc"

    # Daily & session levels from raw M1
    daily_levels = compute_daily_levels(df_m1)
    session_levels = compute_session_levels(df_m1)

    # Add features to M1
    df_m1_feat = add_core_features(df_m1, feature_cfg)

    tf_contexts: Dict[str, TimeframePAContext] = {}

    for tf in tfs:
        if tf == "M1":
            df_tf = df_m1_feat
        else:
            # Resample and add features at TF level
            df_tf_raw = resample_tf(df_m1_feat, tf)
            df_tf = add_core_features(df_tf_raw, feature_cfg)

        ctx_tf = _build_single_tf_context(tf, df_tf, feature_cfg)
        tf_contexts[tf] = ctx_tf

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


def build_pa_context_for_instrument(
    instrument: str,
    hours_back: int = 24,
    tfs: Sequence[str] = ("M1", "M5", "M15", "H1"),
    feature_cfg: Optional[FeatureConfig] = None,
) -> PAContext:
    """
    Convenience wrapper: load M1 candles from DB and build PAContext.

    Used both for:
      - live analysis (last X hours)
      - backtest snippets (for a given window)
    """
    end = datetime.now(timezone.utc)
    start = end - pd.Timedelta(hours=hours_back)

    df_m1 = load_m1_candles(instrument, start, end)
    return build_pa_context_from_m1(
        instrument=instrument,
        df_m1=df_m1,
        tfs=tfs,
        feature_cfg=feature_cfg,
    )


# ---------- Optional: compact dict for LLM / logging ----------

def pa_context_to_dict(ctx: PAContext) -> dict:
    """
    Convert PAContext into a compact, JSON-serializable dict suitable for:
      - LLM prompts
      - Logging
      - Dashboard APIs
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
        # Swings summary: last few swings only
        swings_summary = []
        for s in tf_ctx.swings[-10:]:
            swings_summary.append(
                {
                    "ts": s.ts.isoformat(),
                    "price": float(s.price),
                    "type": s.type.value,
                    "rel_label": s.rel_label,
                }
            )

        # Trend
        trend_dict = {
            "state": tf_ctx.trend.state.value if tf_ctx.trend.state is not None else None,
            "reason": tf_ctx.trend.reason,
        }

        # OB & FVG counts, and top few scored OBs
        # (We don't dump full objects here to keep payload small)
        obs_sorted = sorted(
            tf_ctx.order_blocks,
            key=lambda ob: (ob.score or 0.0),
            reverse=True,
        )
        ob_summary = []
        for ob in obs_sorted[:5]:
            ob_summary.append(
                {
                    "ts": ob.ts.isoformat(),
                    "type": ob.type.value,
                    "low": ob.low,
                    "high": ob.high,
                    "body_low": ob.body_low,
                    "body_high": ob.body_high,
                    "score": ob.score,
                }
            )

        fvg_summary = []
        for f in tf_ctx.fvg_list[-10:]:
            fvg_summary.append(
                {
                    "ts_start": f.ts_start.isoformat(),
                    "ts_end": f.ts_end.isoformat(),
                    "direction": f.direction.value,
                    "gap_low": f.gap_low,
                    "gap_high": f.gap_high,
                    "is_filled": f.is_filled,
                }
            )

        out["tfs_detail"][tf] = {
            "swings": swings_summary,
            "trend": trend_dict,
            "order_blocks": ob_summary,
            "fvg": fvg_summary,
        }

    return out
