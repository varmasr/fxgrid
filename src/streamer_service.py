# src/streamer_service.py

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from .config_loader import load_settings, Settings
from .mt5_client import MT5Client, MT5BrokerConfig
from .timescale_repo import TimescaleRepo


class StreamerService:
    def __init__(self, job_name: str):
        # Create a logger per instance/module
        self.logger = logging.getLogger(__name__)

        self.job_name = job_name
        self.logger.info("Initializing StreamerService for job '%s'", job_name)

        # 1) Load full settings
        self.settings: Settings = load_settings(job_name)

        # 2) Get this job's config
        job_cfg = self.settings.streaming_jobs[job_name]

        # 3) Broker block
        broker_cfg_raw: Dict[str, Any] = self.settings.brokers[job_cfg.broker_key]
        tz_raw = broker_cfg_raw["timezone"]
        utc_offset_hours = tz_raw.get("utc_offset_hours", 0)

        conn_env = broker_cfg_raw["connection_env"]

        # 4) Build MT5BrokerConfig
        broker_cfg = MT5BrokerConfig(
            login=int(self._get_env(conn_env["login"])),
            password=self._get_env(conn_env["password"]),
            server=self._get_env(conn_env["server"]),
            utc_offset_hours=utc_offset_hours,
        )

        # 5) Job-level info
        self.broker_key = job_cfg.broker_key
        self.account_key = job_cfg.account_key
        self.instruments = job_cfg.instruments
        self.timeframe = job_cfg.timeframe
        self.poll_interval_seconds = job_cfg.poll_interval_seconds
        self.lookback_minutes_on_each_poll = job_cfg.lookback_minutes_on_each_poll
        self.max_backfill_hours_on_startup = job_cfg.max_backfill_hours_on_startup

        # 6) Account info
        account_cfg = broker_cfg_raw["accounts"][self.account_key]
        self.account_id = account_cfg["account_id"]

        self.logger.info(
            "Broker key: %s | Account key: %s (%s) | Instruments: %s | TF: %s",
            self.broker_key,
            self.account_key,
            self.account_id,
            ", ".join(self.instruments),
            self.timeframe,
        )

        # 7) DB + MT5 client
        self.db = TimescaleRepo(self.settings.db)
        self.mt5_client = MT5Client(broker_cfg)

        self.system_source = self.settings.system.source_tag
        self.created_by = self.settings.system.created_by

    @staticmethod
    def _get_env(key: str) -> str:
        import os
        val = os.getenv(key)
        if val is None:
            raise RuntimeError(f"Environment variable '{key}' is not set")
        return val

    def _now_utc(self) -> datetime:
        return datetime.now(timezone.utc)

    def _compute_startup_range(self, instrument: str) -> datetime:
        last_ts = self.db.get_last_timestamp_utc(instrument)
        now_utc = self._now_utc()

        if last_ts is None:
            start_utc = now_utc - timedelta(hours=self.max_backfill_hours_on_startup)
            self.logger.info(
                "[%s] No existing rows, starting backfill from %s (max_backfill %d h)",
                instrument,
                start_utc.isoformat(),
                self.max_backfill_hours_on_startup,
            )
            return start_utc

        self.logger.info("[%s] Last timestamp in DB: %s", instrument, last_ts.isoformat())
        return last_ts - timedelta(minutes=2)
    
    def _filter_only_closed_candles(self, candles):
        """
        Remove the currently-forming candle.
        A candle is considered CLOSED if:
        - its timestamp_utc < current UTC minute
        """
        now_utc = self._now_utc()
        current_minute = now_utc.replace(second=0, microsecond=0)

        return [
            c for c in candles
            if c.timestamp_utc < current_minute
        ]


    def initial_backfill(self) -> None:
        """
        On startup, fetch a chunk of recent candles and insert only what is missing.

        We avoid time-window queries and instead ask MT5 for "last N" candles,
        then filter them by:
          - timestamp_utc >= now_utc - max_backfill_hours_on_startup
          - timestamp_utc > last_ts_in_db (if exists)
        """
        self.logger.info("Starting initial backfill for job '%s'", self.job_name)
        now_utc = self._now_utc()

        # How many M1 candles do we need to cover max_backfill_hours?
        # 60 bars per hour * hours + some safety margin
        bars_per_hour = 60
        max_bars = self.max_backfill_hours_on_startup * bars_per_hour + 50

        min_allowed_ts = now_utc - timedelta(hours=self.max_backfill_hours_on_startup)

        for inst in self.instruments:
            last_ts = self.db.get_last_timestamp_utc(inst)
            self.logger.info(
                "[%s] Last timestamp in DB before backfill: %s",
                inst,
                last_ts.isoformat() if last_ts else "None",
            )

            raw_candles = self.mt5_client.copy_rates_recent(inst, self.timeframe, max_bars)
            # Remove current forming candle
            raw_candles = self._filter_only_closed_candles(raw_candles)

            self.logger.info(
                "[%s] Initial backfill fetched %d recent candles from MT5",
                inst,
                len(raw_candles),
            )

            # Filter by max_backfill window
            filtered = [
                c for c in raw_candles
                if c.timestamp_utc >= min_allowed_ts
            ]

            # Further filter out anything already in DB
            if last_ts is not None:
                filtered = [c for c in filtered if c.timestamp_utc > last_ts]

            self.logger.info(
                "[%s] After filtering, %d candles remain to insert",
                inst,
                len(filtered),
            )

            if not filtered:
                continue

            self.db.insert_candles(
                filtered,
                system_source=self.system_source,
                created_by=self.created_by,
                account_id=self.account_id,
            )


    def _poll_once(self) -> None:
        """
        Periodic poll:

        1) For each instrument, get last N candles from MT5 (small N, e.g. lookback_minutes+5).
        2) Filter by timestamp_utc > last_ts_in_db.
        3) Insert whatever is new.
        """
        now_utc = self._now_utc()

        # M1: 1 bar per minute, so minutes + small safety margin
        bars_per_minute = 1
        max_bars = self.lookback_minutes_on_each_poll * bars_per_minute + 5

        for inst in self.instruments:
            last_ts = self.db.get_last_timestamp_utc(inst)
            self.logger.debug("[%s] Last timestamp in DB: %s", inst, last_ts)

            raw_candles = self.mt5_client.copy_rates_recent(inst, self.timeframe, max_bars)
            raw_candles = self._filter_only_closed_candles(raw_candles)

            self.logger.info(
                "[%s] Poll fetched %d recent candles from MT5",
                inst,
                len(raw_candles),
            )

            # If DB has data, keep only new candles
            if last_ts is not None:
                new_candles = [c for c in raw_candles if c.timestamp_utc > last_ts]
            else:
                # If no data at all, keep all
                new_candles = raw_candles

            self.logger.info(
                "[%s] New candles after DB filter: %d",
                inst,
                len(new_candles),
            )

            if not new_candles:
                continue

            self.db.insert_candles(
                new_candles,
                system_source=self.system_source,
                created_by=self.created_by,
                account_id=self.account_id,
            )


    def run_forever(self) -> None:
        import traceback

        self.logger.info(
            "Starting streamer job '%s' (poll_interval=%ss, lookback=%s min)...",
            self.job_name,
            self.poll_interval_seconds,
            self.lookback_minutes_on_each_poll,
        )

        while True:
            try:
                self.logger.info("Connecting to MT5...")
                self.mt5_client.connect()
                self.logger.info("Connected to MT5. Running initial backfill...")
                self.initial_backfill()
                self.logger.info("Initial backfill completed. Entering polling loop.")

                while True:
                    self._poll_once()
                    time.sleep(self.poll_interval_seconds)

            except Exception as e:
                self.logger.error("Error in streaming loop: %s", e, exc_info=True)
                try:
                    self.mt5_client.shutdown()
                except Exception:
                    pass
                self.logger.info("Sleeping 10 seconds before retrying...")
                time.sleep(10)
