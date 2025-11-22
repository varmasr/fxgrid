# tests/test_pa_context.py

from pa_engine.pa.context import build_pa_context_for_instrument, pa_context_to_dict
from pa_engine.pa.trend import TrendStateEnum


def test_build_pa_context_usdjpy():
    # This assumes you have recent USDJPY M1 data in your DB (last 6h).
    ctx = build_pa_context_for_instrument("USDJPY", hours_back=6)

    assert ctx.instrument == "USDJPY"
    assert "M15" in ctx.tfs
    assert "M15" in ctx.tf_contexts

    tf_ctx = ctx.tf_contexts["M15"]
    # There should be some candles
    assert not tf_ctx.df.empty

    # Trend state should be one of the defined enums or None if empty
    if tf_ctx.trend.state is not None:
        assert tf_ctx.trend.state in {
            TrendStateEnum.UP,
            TrendStateEnum.DOWN,
            TrendStateEnum.RANGE,
            TrendStateEnum.UNCLEAR,
        }

    # OB and FVG engines should not crash; they may return 0+ objects
    assert isinstance(tf_ctx.order_blocks, list)
    assert isinstance(tf_ctx.fvg_list, list)

    # Dict conversion should work and be JSON-like
    ctx_dict = pa_context_to_dict(ctx)
    assert ctx_dict["instrument"] == "USDJPY"
    assert "M15" in ctx_dict["tfs_detail"]
