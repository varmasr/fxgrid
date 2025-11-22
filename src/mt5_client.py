from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import MetaTrader5 as mt5

logger = logging.getLogger(__name__)


@dataclass
class MT5BrokerConfig:
    """
    Broker configuration for MT5 connection.

    utc_offset_hours:
        Broker/server time minus UTC. Example:
          - Broker UTC+2  -> utc_offset_hours = 2
          - Broker UTC-3  -> utc_offset_hours = -3

        MT5's rates['time'] behaves as SERVER time encoded as epoch.
        So to get true UTC we must subtract this offset.
    """
    login: int
    password: str
    server: str
    utc_offset_hours: Optional[int] = None


@dataclass
class Candle:
    """
    Internal candle representation. timestamp_utc is ALWAYS true UTC.
    """
    instrument: str
    timestamp_utc: datetime
    bid_open: float
    bid_high: float
    bid_low: float
    bid_close: float
    ask_open: Optional[float]
    ask_high: Optional[float]
    ask_low: Optional[float]
    ask_close: Optional[float]
    volume: int
    tick_count: int


TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1,
}


class MT5Client:
    def __init__(self, cfg: MT5BrokerConfig):
        self.cfg = cfg
        # Broker/server offset vs UTC (e.g. UTC+2 -> +2h)
        offset_hours = cfg.utc_offset_hours if cfg.utc_offset_hours is not None else 0
        self.server_offset = timedelta(hours=offset_hours)

        logger.info(
            "MT5Client initialized for server '%s', login=%s, server UTC offset=%+d h",
            cfg.server,
            cfg.login,
            offset_hours,
        )

    # ------------------------------------------------------------------ #
    # Connection management                                              #
    # ------------------------------------------------------------------ #
    def connect(self) -> None:
        """
        Initialize MetaTrader 5 against the default installed terminal and log in.
        """
        logger.info("Initializing MT5 using default terminal...")
        if not mt5.initialize():
            err = mt5.last_error()
            logger.error("MT5 initialize failed: %s", err)
            raise RuntimeError(f"MT5 initialize failed: {err}")

        logger.info("Logging in to server '%s' with login=%s", self.cfg.server, self.cfg.login)
        authorized = mt5.login(self.cfg.login, password=self.cfg.password, server=self.cfg.server)
        if not authorized:
            err = mt5.last_error()
            logger.error("MT5 login failed: %s", err)
            raise RuntimeError(f"MT5 login failed: {err}")

        logger.info("Connected to MT5: login=%s server=%s", self.cfg.login, self.cfg.server)

    def shutdown(self) -> None:
        logger.info("Shutting down MT5 connection...")
        mt5.shutdown()
        logger.info("MT5 connection shutdown")

    # ------------------------------------------------------------------ #
    # Core candle conversion                                             #
    # ------------------------------------------------------------------ #
    def _build_candles_from_rates(self, symbol: str, rates) -> List[Candle]:
        """
        Convert MT5 structured array to our Candle list with **true UTC** timestamps.

        MT5 behaviour (from your tests):
          - rates['time'] encodes SERVER time as epoch (UTC+offset).
        So:
          1) server_time_utc_like = utcfromtimestamp(epoch)
          2) true_utc = server_time_utc_like - server_offset
        """
        if rates is None or len(rates) == 0:
            return []

        field_names = rates.dtype.names or ()
        has_real_volume = "real_volume" in field_names
        has_tick_volume = "tick_volume" in field_names

        candles: List[Candle] = []
        for r in rates:
            epoch = int(r["time"])

            # Step 1: interpret epoch as "server time but labelled as UTC"
            server_utc_like = datetime.utcfromtimestamp(epoch).replace(tzinfo=timezone.utc)

            # Step 2: subtract broker offset to get true UTC
            ts_utc = server_utc_like - self.server_offset

            bid_open = float(r["open"])
            bid_high = float(r["high"])
            bid_low = float(r["low"])
            bid_close = float(r["close"])

            # Right now MT5 only gives us one OHLC stream.
            # For FX this is effectively BID. We mirror it to ASK for now;
            # you can later model spreads explicitly if needed.
            ask_open = bid_open
            ask_high = bid_high
            ask_low = bid_low
            ask_close = bid_close

            if has_real_volume:
                volume = int(r["real_volume"])
            elif has_tick_volume:
                volume = int(r["tick_volume"])
            else:
                volume = 0

            if has_tick_volume:
                tick_count = int(r["tick_volume"])
            else:
                tick_count = volume

            candles.append(
                Candle(
                    instrument=symbol,
                    timestamp_utc=ts_utc,
                    bid_open=bid_open,
                    bid_high=bid_high,
                    bid_low=bid_low,
                    bid_close=bid_close,
                    ask_open=ask_open,
                    ask_high=ask_high,
                    ask_low=ask_low,
                    ask_close=ask_close,
                    volume=volume,
                    tick_count=tick_count,
                )
            )

        candles.sort(key=lambda c: c.timestamp_utc)
        logger.debug("Built %d Candle objects for %s", len(candles), symbol)
        return candles

    # ------------------------------------------------------------------ #
    # Live-friendly retrieval: last N candles                            #
    # ------------------------------------------------------------------ #
    def copy_rates_recent(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> List[Candle]:
        """
        Fetch the most recent `limit` candles for `symbol` / `timeframe` using
        mt5.copy_rates_from_pos, which is position-based and avoids any timezone
        windowing issues.

        The latest MT5 candle will ALWAYS appear in this list. After conversion
        with _build_candles_from_rates and DB dedup on timestamp_utc, the latest
        MT5 candle will be the latest row in the DB (in true UTC).
        """
        if timeframe not in TIMEFRAME_MAP:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        tf = TIMEFRAME_MAP[timeframe]

        logger.debug("Requesting last %d candles for %s (%s)", limit, symbol, timeframe)

        rates = mt5.copy_rates_from_pos(symbol, tf, 0, limit)
        if rates is None:
            err = mt5.last_error()
            logger.warning("copy_rates_from_pos returned None for %s: %s", symbol, err)
            return []

        if len(rates) == 0:
            logger.debug("copy_rates_from_pos returned empty array for %s", symbol)
            return []

        return self._build_candles_from_rates(symbol, rates)

    # Optional range API, built on top of recent + UTC filtering
    def copy_rates_range(
        self,
        symbol: str,
        timeframe: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> List[Candle]:
        """
        Range wrapper implemented via over-fetching with copy_rates_recent and
        filtering by UTC. Currently not used by the streaming service.
        """
        if start_utc.tzinfo is None:
            start_utc = start_utc.replace(tzinfo=timezone.utc)
        else:
            start_utc = start_utc.astimezone(timezone.utc)

        if end_utc.tzinfo is None:
            end_utc = end_utc.replace(tzinfo=timezone.utc)
        else:
            end_utc = end_utc.astimezone(timezone.utc)

        seconds = (end_utc - start_utc).total_seconds()
        approx_bars = max(1, int(seconds // 60) + 5)

        raw = self.copy_rates_recent(symbol, timeframe, approx_bars)
        return [c for c in raw if start_utc <= c.timestamp_utc < end_utc]
