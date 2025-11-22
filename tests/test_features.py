# tests/test_features.py

from datetime import datetime, timedelta, timezone

from pa_engine.db.candles import load_m1_candles
from pa_engine.db.resampler import resample_tf
from pa_engine.pa.features import (
    FeatureConfig,
    add_core_features,
    compute_daily_levels,
    compute_session_levels,
)


INSTRUMENT = "USDJPY"  # or any with data


def _load_sample():
    end = datetime.now(timezone.utc)
    start = end.replace(hour=0, minute=0, second=0, microsecond=0)  # start of day UTC
    return load_m1_candles(INSTRUMENT, start, end)


def test_add_core_features_on_m15():
    df_m1 = _load_sample()
    if df_m1.empty:
        # If no data (e.g. weekend), just ensure no crash
        return

    df_m15 = resample_tf(df_m1, "M15")
    cfg = FeatureConfig()

    df_feat = add_core_features(df_m15, cfg)
    print(df_feat.tail())
    # Columns should exist
    assert f"atr_{cfg.atr_period}" in df_feat.columns
    for n in cfg.ema_periods:
        assert f"ema_{n}" in df_feat.columns
    for n in cfg.donchian_periods:
        assert f"donchian_high_{n}" in df_feat.columns
        assert f"donchian_low_{n}" in df_feat.columns


def test_daily_and_session_levels():
    df_m1 = _load_sample()
    if df_m1.empty:
        return

    daily = compute_daily_levels(df_m1)
    print(daily)
    # Should not crash; if enough history, may contain prev_day/current_day
    # Just check structure if keys exist
    if "prev_day" in daily:
        prev = daily["prev_day"]
        assert "high" in prev and "low" in prev and "close" in prev

    if "current_day" in daily:
        curr = daily["current_day"]
        assert "open" in curr

    session = compute_session_levels(df_m1)
    if session:
        assert "sessions" in session
        for sess_name, sess_levels in session["sessions"].items():
            assert "high" in sess_levels and "low" in sess_levels
