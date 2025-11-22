# pa_engine/config/loader.py

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import os
import yaml
from dotenv import load_dotenv

# Load .env once at import time (safe to call multiple times)
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)


@dataclass
class DatabaseConfig:
    host: str
    port: int
    name: str
    user: str
    password: str
    schema: str
    live_table: str
    historical_table: str
    storage_timezone: str
    statement_timeout_ms: int


@dataclass
class SystemConfig:
    name: str
    environment: str
    source_tag: str


@dataclass
class AppConfig:
    system: SystemConfig
    database: DatabaseConfig


def load_settings_yaml(path: Optional[Path] = None) -> dict:
    """
    Load the existing config/settings.yaml used by the streamer.
    """
    if path is None:
        # assuming repo_root/config/settings.yaml
        path = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"

    with open(path, "r") as f:
        return yaml.safe_load(f)


def build_app_config() -> AppConfig:
    raw = load_settings_yaml()

    system_raw = raw["system"]
    db_raw = raw["database"]

    # Resolve DB settings from ENV as specified in settings.yaml
    host = os.getenv(db_raw["host_env"])
    port = int(os.getenv(db_raw["port_env"]))
    name = os.getenv(db_raw["name_env"])
    user = os.getenv(db_raw["user_env"])
    password = os.getenv(db_raw["password_env"])

    db_cfg = DatabaseConfig(
        host=host,
        port=port,
        name=name,
        user=user,
        password=password,
        schema=db_raw.get("schema", "public"),
        live_table=db_raw["live_table"],
        historical_table=db_raw["historical_table"],
        storage_timezone=db_raw.get("storage_timezone", "UTC"),
        statement_timeout_ms=db_raw.get("statement_timeout_ms", 30000),
    )

    sys_cfg = SystemConfig(
        name=system_raw["name"],
        environment=system_raw.get("environment", "dev"),
        source_tag=system_raw.get("source_tag", "pa_engine"),
    )

    return AppConfig(system=sys_cfg, database=db_cfg)
