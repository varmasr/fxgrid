# pa_engine/pa/features.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, Any
from pa_engine.pa.config import FX_DAILY_OPEN_UTC,session_for_hour


import pandas as pd


@dataclass
class FeatureConfig:
    """
    Configuration for core PA features.
    Applies to any timeframe df with:
      index = ts_utc (datetime)
      columns = open, high, low, close, norm_volume
    """
    atr_period: int = 14
    ema_periods: tuple[int, ...] = (20, 50)
    donchian_periods: tuple[int, ...] = (20, 50)


# ---------- Core per-TF features: ATR, EMA, Donchian ----------

def add_core_features(
    df: pd.DataFrame,
    cfg: FeatureConfig | None = None,
) -> pd.DataFrame:
    """
    Add ATR, EMAs, and Donchian channels to a candle dataframe.

    Expects:
      - df.index is datetime (ts_utc)
      - df has columns: open, high, low, close, norm_volume

    Returns a *copy* of df with extra columns:
      - atr_{period}
      - ema_{n}
      - donchian_high_{n}, donchian_low_{n}
    """
    if df.empty:
        return df.copy()

    if cfg is None:
        cfg = FeatureConfig()
    df["session"] = df.index.map(infer_session)

    out = df.copy()

    # --- ATR ---
    if cfg.atr_period is not None and cfg.atr_period > 1:
        out[f"atr_{cfg.atr_period}"] = _compute_atr(out, period=cfg.atr_period)

    # --- EMAs ---
    for n in cfg.ema_periods:
        out[f"ema_{n}"] = out["close"].ewm(span=n, adjust=False).mean()

    # --- Donchian channels ---
    for n in cfg.donchian_periods:
        out[f"donchian_high_{n}"] = out["high"].rolling(window=n, min_periods=1).max()
        out[f"donchian_low_{n}"] = out["low"].rolling(window=n, min_periods=1).min()

    return out


def _compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Simple ATR using SMA of True Range.

    True Range = max(
        high - low,
        abs(high - prev_close),
        abs(low  - prev_close)
    )
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    prev_close = close.shift(1)

    tr1 = (high - low).abs()
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period, min_periods=period).mean()
    return atr


# ---------- Daily levels (prev day HL/C + curr day open) ----------

from pa_engine.pa.config import FX_DAILY_OPEN_UTC  # <-- add this import at top of file

def infer_session(ts: pd.Timestamp) -> str:
    """
    Map a UTC timestamp to a session label, using central config.
    """
    hr = ts.hour  # UTC hour
    return session_for_hour(hr)


def compute_daily_levels(df_m1: pd.DataFrame) -> Dict[str, Any]:
    """
    Compute FX daily levels using the correct FX session boundary:
        Daily FX Candle = 22:00 UTC → 21:59 UTC next day
    """

    result: Dict[str, Any] = {}

    if df_m1.empty:
        return result

    df = df_m1.copy().sort_index()
    last_ts = df.index.max()  # latest M1 candle timestamp

    # ---------------------------------------------
    # Determine FX daily start for "current" day
    # ---------------------------------------------
    # If current time >= 22:00 UTC → today's FX day started at 22:00 same day
    # Else → FX day started yesterday 22:00 UTC
    # Example:
    #   2025-11-21 03:00 UTC --> FX day start = 2025-11-20 22:00 UTC
    #   2025-11-21 23:00 UTC --> FX day start = 2025-11-21 22:00 UTC
    # ---------------------------------------------

    if last_ts.hour >= FX_DAILY_OPEN_UTC:
        current_day_start = last_ts.replace(
            hour=FX_DAILY_OPEN_UTC, minute=0, second=0, microsecond=0
        )
    else:
        prev = last_ts - pd.Timedelta(days=1)
        current_day_start = prev.replace(
            hour=FX_DAILY_OPEN_UTC, minute=0, second=0, microsecond=0
        )

    # Previous FX day start
    prev_day_start = current_day_start - pd.Timedelta(days=1)

    # Candle ranges:
    # prev_day = [prev_day_start, current_day_start - 1s]
    # curr_day = [current_day_start, current_day_start + 24h - 1s]
    prev_day_end = current_day_start - pd.Timedelta(seconds=1)
    current_day_end = current_day_start + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)

    # Slice DF
    df_prev = df[(df.index >= prev_day_start) & (df.index <= prev_day_end)]
    df_curr = df[(df.index >= current_day_start) & (df.index <= current_day_end)]

    # -------------------------
    # Build output dictionary
    # -------------------------
    result["prev_day"] = None
    result["current_day"] = None

    # ------ Previous Day (prev_day_start → current_day_start - 1s) ------
    # Label dates as "close date" (TradingView-style) = start + 1 day
    prev_label_date = (prev_day_start + pd.Timedelta(days=1)).date().isoformat()
    curr_label_date = (current_day_start + pd.Timedelta(days=1)).date().isoformat()

    # Previous day
    if not df_prev.empty:
        result["prev_day"] = {
            "date": prev_label_date,
            "open": float(df_prev.iloc[0]["open"]),
            "close": float(df_prev.iloc[-1]["close"]),
            "high": float(df_prev["high"].max()),
            "low": float(df_prev["low"].min()),
        }

    # Current day
    if not df_curr.empty:
        result["current_day"] = {
            "date": curr_label_date,
            "open": float(df_curr.iloc[0]["open"]),
            "incomplete_day": df_curr.index.max() < current_day_end,
        }


    return result

# ---------- Session levels (Asia / London / NY / Overlap) ----------

def compute_session_levels(df_m1: pd.DataFrame) -> Dict[str, Any]:
    """
    Compute intraday session highs/lows for the *latest calendar day* in the data.

    Uses session labels from infer_session() / session_for_hour():
        SYDNEY, ASIA, LONDON, NEW_YORK, LONDON_NY_OVERLAP
    """
    result: Dict[str, Any] = {}
    if df_m1.empty:
        return result

    df = df_m1.copy().sort_index()

    # Ensure we have a 'session' column
    if "session" not in df.columns:
        df["session"] = df.index.map(infer_session)

    # Use latest calendar date in the data (UTC) for session levels
    dates = df.index.date
    unique_dates = sorted(set(dates))
    if not unique_dates:
        return result

    curr_day = unique_dates[-1]
    df_curr = df[df.index.date == curr_day]
    if df_curr.empty:
        return result

    sessions_info: Dict[str, Dict[str, float]] = {}
    for sess in ["ASIA", "LONDON", "NEW_YORK", "NY_OVERLAP"]:
        sub = df_curr[df_curr["session"] == sess]
        if sub.empty:
            continue
        sessions_info[sess] = {
            "high": float(sub["high"].max()),
            "low": float(sub["low"].min()),
        }

    if sessions_info:
        result["date"] = curr_day.isoformat()
        result["sessions"] = sessions_info

    return result
