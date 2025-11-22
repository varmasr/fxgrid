# src/config_loader.py

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Any

import yaml

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"
SETTINGS_FILE = CONFIG_DIR / "settings.yaml"
ENV_FILE = CONFIG_DIR / ".env"


@dataclass
class BrokerTimezoneConfig:
    mode: str                # "fixed_offset" or "iana" (future)
    utc_offset_hours: int | None = None
    iana_name: str | None = None


@dataclass
class StreamingJobConfig:
    name: str
    broker_key: str
    account_key: str
    instruments: List[str]
    timeframe: str
    poll_interval_seconds: int
    lookback_minutes_on_each_poll: int
    max_backfill_hours_on_startup: int


@dataclass
class DatabaseConfig:
    schema: str
    live_table: str
    historical_table: str
    storage_timezone: str
    host: str
    port: int
    name: str
    user: str
    password: str
    default_data_quality_score: int
    statement_timeout_ms: int


@dataclass
class SystemConfig:
    name: str
    environment: str
    created_by: str
    source_tag: str


@dataclass
class Settings:
    system: SystemConfig
    db: DatabaseConfig
    brokers: Dict[str, Dict[str, Any]]
    streaming_defaults: Dict[str, Any]
    streaming_jobs: Dict[str, StreamingJobConfig]


def _load_env() -> None:
    """Load .env explicitly from config/.env."""
    if load_dotenv is not None:
        load_dotenv(ENV_FILE)
    else:
        # Fallback: .env should already be loaded by the environment
        pass


def _read_yaml() -> Dict[str, Any]:
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_settings(job_name: str) -> Settings:
    """
    Load full settings + resolve database credentials + pick a streaming job.
    """
    _load_env()
    raw = _read_yaml()

    system_raw = raw["system"]
    system = SystemConfig(
        name=system_raw["name"],
        environment=system_raw["environment"],
        created_by=system_raw["created_by"],
        source_tag=system_raw["source_tag"],
    )

    db_raw = raw["database"]
    db = DatabaseConfig(
        schema=db_raw["schema"],
        live_table=db_raw["live_table"],
        historical_table=db_raw["historical_table"],
        storage_timezone=db_raw["storage_timezone"],
        host=os.getenv(db_raw.get("host_env", "DB_HOST"), "localhost"),
        port=int(os.getenv(db_raw.get("port_env", "DB_PORT"), "5432")),
        name=os.getenv(db_raw.get("name_env", "DB_NAME"), "fx_core"),
        user=os.getenv(db_raw.get("user_env", "DB_USER")),
        password=os.getenv(db_raw.get("password_env", "DB_PASSWORD")),
        default_data_quality_score=db_raw["default_data_quality_score"],
        statement_timeout_ms=db_raw.get("statement_timeout_ms", 30000),
    )

    brokers = raw["brokers"]
    streaming_defaults = raw["streaming"]["defaults"]
    all_jobs_raw = raw["streaming"]["jobs"]

    if job_name not in all_jobs_raw:
        raise ValueError(f"Streaming job '{job_name}' not found in settings.yaml")

    # Build StreamingJobConfig objects for all jobs; we’ll still keep them all
    jobs: Dict[str, StreamingJobConfig] = {}
    for name, j in all_jobs_raw.items():
        jobs[name] = StreamingJobConfig(
            name=name,
            broker_key=j["broker_key"],
            account_key=j["account_key"],
            instruments=j["instruments"],
            timeframe=j.get("timeframe", streaming_defaults["timeframe"]),
            poll_interval_seconds=j.get(
                "poll_interval_seconds", streaming_defaults["poll_interval_seconds"]
            ),
            lookback_minutes_on_each_poll=j.get(
                "lookback_minutes_on_each_poll",
                streaming_defaults["lookback_minutes_on_each_poll"],
            ),
            max_backfill_hours_on_startup=j.get(
                "max_backfill_hours_on_startup",
                streaming_defaults["max_backfill_hours_on_startup"],
            ),
        )

    return Settings(
        system=system,
        db=db,
        brokers=brokers,
        streaming_defaults=streaming_defaults,
        streaming_jobs=jobs,
    )
