# src/timescale_repo.py

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, List

import psycopg2
import psycopg2.extras

from .mt5_client import Candle
from .config_loader import DatabaseConfig

logger = logging.getLogger(__name__)


@dataclass
class TimescaleRepo:
    cfg: DatabaseConfig

    def _connect(self):
        conn = psycopg2.connect(
            host=self.cfg.host,
            port=self.cfg.port,
            dbname=self.cfg.name,
            user=self.cfg.user,
            password=self.cfg.password,
            connect_timeout=10,
        )
        with conn.cursor() as cur:
            cur.execute(f"SET statement_timeout = {self.cfg.statement_timeout_ms};")
            cur.execute("SET TIME ZONE 'UTC';")
        return conn

    def get_last_timestamp_utc(self, instrument: str) -> Optional[datetime]:
        query = f"""
            SELECT max("timestamp") AS last_ts
            FROM {self.cfg.schema}.{self.cfg.live_table}
            WHERE instrument = %s;
        """
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(query, (instrument,))
                row = cur.fetchone()
                if row and row[0] is not None:
                    # row[0] is already timestamptz in UTC
                    return row[0].astimezone(timezone.utc)
                return None
        finally:
            conn.close()

    def insert_candles(self, candles: List[Candle], system_source: str, created_by: str, account_id: str):
        if not candles:
            return

        insert_sql = f"""
            INSERT INTO {self.cfg.schema}.{self.cfg.live_table} (
                instrument,
                "timestamp",
                bid_open,
                bid_high,
                bid_low,
                bid_close,
                ask_open,
                ask_high,
                ask_low,
                ask_close,
                volume,
                tick_count,
                source,
                account_id,
                data_quality_score,
                processing_latency_ms,
                received_at,
                created_by
            )
            VALUES (
                %(instrument)s,
                %(timestamp)s,
                %(bid_open)s,
                %(bid_high)s,
                %(bid_low)s,
                %(bid_close)s,
                %(ask_open)s,
                %(ask_high)s,
                %(ask_low)s,
                %(ask_close)s,
                %(volume)s,
                %(tick_count)s,
                %(source)s,
                %(account_id)s,
                %(data_quality_score)s,
                %(processing_latency_ms)s,
                %(received_at)s,
                %(created_by)s
            )
            ON CONFLICT (instrument, "timestamp") DO NOTHING;
        """

        now_utc = datetime.now(timezone.utc)
        rows = []
        for c in candles:
            latency_ms = int((now_utc - c.timestamp_utc).total_seconds() * 1000)

            rows.append(
                {
                    "instrument": c.instrument,
                    "timestamp": c.timestamp_utc,
                    "bid_open": c.bid_open,
                    "bid_high": c.bid_high,
                    "bid_low": c.bid_low,
                    "bid_close": c.bid_close,
                    "ask_open": c.ask_open,
                    "ask_high": c.ask_high,
                    "ask_low": c.ask_low,
                    "ask_close": c.ask_close,
                    "volume": c.volume,
                    "tick_count": c.tick_count,
                    "source": system_source,
                    "account_id": account_id,
                    "data_quality_score": self.cfg.default_data_quality_score,
                    "processing_latency_ms": latency_ms,
                    "received_at": now_utc,
                    "created_by": created_by,
                }
            )


        conn = self._connect()
        try:
            with conn.cursor() as cur:
                psycopg2.extras.execute_batch(cur, insert_sql, rows, page_size=100)
            conn.commit()
            logger.info("Inserted %d candles into %s", len(rows), self.cfg.live_table)
        except Exception as e:
            conn.rollback()
            logger.exception("Failed to insert candles: %s", e)
            raise
        finally:
            conn.close()
