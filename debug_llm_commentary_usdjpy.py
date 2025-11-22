# debug_llm_commentary_usdjpy.py

from datetime import datetime, timezone
import os

import pandas as pd
from dotenv import load_dotenv  # pip install python-dotenv

from openai import OpenAI

from pa_engine.db.candles import load_m1_candles
from pa_engine.pa.features import FeatureConfig
from pa_engine.pa.context import build_pa_context_from_m1
from pa_engine.pa.strategy_context import build_strategy_context
from pa_engine.llm.commentary import (
    LLMCommentaryConfig,
    generate_market_commentary,
)


def main():
    instrument = "USDJPY"
    hours_back = 24

    # 0) Load .env and get API key
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        print("ERROR: OPEN_API_KEY not found in environment/.env")
        print("Please add OPEN_API_KEY=your_key to .env and retry.")
        return

    client = OpenAI(api_key=api_key)

    # 1) Load raw M1 candles
    end = datetime.now(timezone.utc)
    start = end - pd.Timedelta(hours=hours_back)

    df_m1 = load_m1_candles(instrument, start, end)
    if df_m1.empty:
        print("No M1 data loaded.")
        return

    # 2) Build PAContext (this resamples to M5/M15 internally)
    feature_cfg = FeatureConfig()
    pa_ctx = build_pa_context_from_m1(
        instrument=instrument,
        df_m1=df_m1,
        feature_cfg=feature_cfg,
        tfs=["M1", "M5", "M15"],  # can add "H1" later if needed
    )

    # 3) Build StrategyContext for base_tf = M5, HTF = M15
    strat_ctx = build_strategy_context(
        pa_ctx=pa_ctx,
        instrument=instrument,
        base_tf="M5",
        htf_tf="M15",
    )

    # 4) Print debug view of StrategyContext
    print("=== StrategyContext (compact dict) ===")
    from pprint import pprint
    pprint(strat_ctx.to_dict())

    # 5) Generate LLM commentary using real OpenAI client
    cfg = LLMCommentaryConfig(
        model="gpt-4.1-mini",  # or "gpt-4.1" if you prefer
        temperature=0.4,
        max_tokens=600,
    )

    commentary = generate_market_commentary(
        client=client,
        strat_ctx=strat_ctx,
        pa_ctx=pa_ctx,
        cfg=cfg,
    )

    print("\n=== LLM Commentary ===")
    print(commentary)


if __name__ == "__main__":
    main()
