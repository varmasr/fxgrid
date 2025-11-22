# pa_engine/db/resampler.py

import pandas as pd

TF_RULES = {
    "M5": "5min",
    "M15": "15min",
    "H1": "1h",
}

def resample_tf(df_m1: pd.DataFrame, tf: str) -> pd.DataFrame:
    """
    Resample 1-minute dataframe into a higher timeframe:
    tf = 'M5', 'M15', or 'H1'

    Returned dataframe has canonical schema:
      index = ts_utc
      open, high, low, close, norm_volume
    """
    if df_m1.empty:
        return df_m1.copy()

    if tf not in TF_RULES:
        raise ValueError(f"Unsupported TF: {tf}. Choose from {list(TF_RULES.keys())}.")

    rule = TF_RULES[tf]

    # Resample OHLC
    ohlc = df_m1[['open', 'high', 'low', 'close']].resample(rule).agg({
        'open': 'first',
        'high': 'max',
        'low':  'min',
        'close': 'last'
    })

    # Resample volume (sum)
    vol = df_m1['norm_volume'].resample(rule).sum()

    # Combine
    out = ohlc.copy()
    out['norm_volume'] = vol

    # Drop periods where open/close are NaN (no M1 data)
    out = out.dropna(subset=['open', 'close'])

    return out
