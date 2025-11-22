# debug_pa_context_usdjpy.py

from datetime import datetime, timezone

import pandas as pd

from pa_engine.pa.context import (
    build_pa_context_for_instrument,
    pa_context_to_dict,
)
from pa_engine.pa.trend import TrendStateEnum


def print_header(title: str):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80 + "\n")


def print_tf_context(tf: str, tf_ctx):
    df = tf_ctx.df

    print_header(f"Timeframe: {tf}")

    # --- Last 5 candles ---
    print("Last 5 candles (OHLC):")
    if not df.empty:
        print(df[["open", "high", "low", "close"]].tail(5))
    else:
        print("  [No data]")
        return

    # --- Trend ---
    trend = tf_ctx.trend
    state = trend.state.value if trend.state else None
    print("\nTrend:")
    print(f"  State : {state}")
    print(f"  Reason: {trend.reason}")

    # --- Swings ---
    print("\nLast 5 swings:")
    if tf_ctx.swings:
        for s in tf_ctx.swings[-5:]:
            print(
                f"  {s.ts.isoformat()} | "
                f"type={s.type.value:4s} | "
                f"price={float(s.price):.5f} | "
                f"rel_label={s.rel_label}"
            )
    else:
        print("  [No swings]")

    # --- Order Blocks ---
    print("\nTop 3 Order Blocks (by score):")
    if tf_ctx.order_blocks:
        obs_sorted = sorted(
            tf_ctx.order_blocks,
            key=lambda ob: (ob.score or 0.0),
            reverse=True,
        )
        for ob in obs_sorted[:3]:
            mid = (ob.low + ob.high) / 2.0
            print(
                f"  {ob.ts.isoformat()} | type={ob.type.value:6s} | "
                f"low={ob.low:.5f} high={ob.high:.5f} mid={mid:.5f} "
                f"body=[{ob.body_low:.5f}, {ob.body_high:.5f}] "
                f"score={ob.score:.2f}"
            )
    else:
        print("  [No order blocks]")

    # --- FVGs ---
    print("\nLast 3 Fair Value Gaps:")
    if tf_ctx.fvg_list:
        for f in tf_ctx.fvg_list[-3:]:
            print(
                f"  {f.ts_start.isoformat()} → {f.ts_end.isoformat()} | "
                f"dir={f.direction.value:7s} | "
                f"gap=[{f.gap_low:.5f}, {f.gap_high:.5f}] | "
                f"size_abs={f.size_abs:.5f} "
                f"is_filled={f.is_filled}"
            )
    else:
        print("  [No FVGs]")

    # --- Liquidity Levels ---
    print("\nTop 5 Liquidity Levels:")
    if tf_ctx.liquidity_levels:
        for lvl in tf_ctx.liquidity_levels[:5]:
            print(
                f"  {lvl.ts.isoformat()} | type={lvl.type.value:10s} | "
                f"price={lvl.price:.5f} | touches={lvl.touches}"
            )
    else:
        print("  [No liquidity levels]")

    # --- Liquidity Sweeps ---
    print("\nLast 5 Liquidity Sweeps:")
    if tf_ctx.liquidity_sweeps:
        for sw in tf_ctx.liquidity_sweeps[-5:]:
            print(
                f"  {sw.ts.isoformat()} | "
                f"level_type={sw.level.type.value:10s} | "
                f"side={sw.side.value:9s} | "
                f"level={sw.level.price:.5f} | "
                f"high={sw.high:.5f} low={sw.low:.5f} close={sw.close:.5f} | "
                f"score={getattr(sw, 'score', 0.0):.2f}"
            )
    else:
        print("  [No sweeps]")


def main():
    instrument = "USDJPY"
    hours_back = 36  # pick enough history to cover all TFs nicely
    tfs = ("M1", "M5", "M15", "H1")

    print_header(f"Building PAContext for {instrument} (last {hours_back}h)")

    ctx = build_pa_context_for_instrument(
        instrument=instrument,
        hours_back=hours_back,
        tfs=tfs,
    )

    ctx_dict = pa_context_to_dict(ctx)

    print("=== PAContext Summary ===")
    print(f"Instrument : {ctx_dict['instrument']}")
    print(f"As of UTC  : {ctx_dict['asof_utc']}")
    print(f"Base TF    : {ctx_dict['base_tf']}")
    print(f"TFs        : {ctx_dict['tfs']}")
    print("\nDaily Levels:")
    print(ctx_dict["daily_levels"])
    print("\nSession Levels:")
    print(ctx_dict["session_levels"])

    # Per-TF details
    for tf in tfs:
        tf_ctx = ctx.tf_contexts.get(tf)
        if tf_ctx is None:
            print_header(f"Timeframe: {tf} (NO CONTEXT)")
            print("  [Missing timeframe context]")
            continue

        print_tf_context(tf, tf_ctx)


if __name__ == "__main__":
    main()
