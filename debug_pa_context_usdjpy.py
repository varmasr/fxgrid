# debug_pa_context_usdjpy.py

from pprint import pprint

from pa_engine.pa.context import build_pa_context_for_instrument, pa_context_to_dict

if __name__ == "__main__":
    ctx = build_pa_context_for_instrument("USDJPY", hours_back=24)
    ctx_dict = pa_context_to_dict(ctx)

    print("=== PAContext Summary for USDJPY ===")
    print(f"asof_utc: {ctx_dict['asof_utc']}")
    print(f"tfs: {ctx_dict['tfs']}")

    print("\n=== Daily Levels ===")
    pprint(ctx_dict["daily_levels"])

    print("\n=== Session Levels ===")
    pprint(ctx_dict["session_levels"])

    print("\n=== M15 Trend + OB/FVG Summary ===")
    m15 = ctx_dict["tfs_detail"]["M15"]
    pprint(m15["trend"])
    print("\nTop OBs:")
    pprint(m15["order_blocks"])
    print("\nRecent FVGs:")
    pprint(m15["fvg"])
