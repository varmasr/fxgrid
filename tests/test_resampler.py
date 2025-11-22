from datetime import datetime, timedelta, timezone
from pa_engine.db.candles import load_m1_candles
from pa_engine.db.resampler import resample_tf

def test_resampler_m5():
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=1)

    df_m1 = load_m1_candles("USDJPY", start, end)
    assert df_m1 is not None

    df_m5 = resample_tf(df_m1, "M5")
    assert df_m5 is not None
    assert all(col in df_m5.columns for col in ['open','high','low','close','norm_volume'])

def test_resampler_time_index():
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=2)

    df_m1 = load_m1_candles("EURUSD", start, end)
    df_m15 = resample_tf(df_m1, "M15")

    assert df_m15.index.is_monotonic_increasing
    assert str(df_m15.index.dtype).startswith("datetime64")

df_m1 = load_m1_candles("USDJPY", datetime(2025, 10, 30, 11, 20, tzinfo=timezone.utc),
                         datetime(2025, 11, 20, 11, 50, tzinfo=timezone.utc))
df_m5 = resample_tf(df_m1, "M5")

print(df_m5.head())
print(df_m5.tail())