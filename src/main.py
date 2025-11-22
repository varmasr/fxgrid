# src/main.py

from __future__ import annotations

import argparse
import logging
from logging.config import dictConfig
from pathlib import Path

from .streamer_service import StreamerService
from .config_loader import _read_yaml


def setup_logging():
    raw_cfg = _read_yaml()
    log_cfg = raw_cfg.get("logging", {})
    level = log_cfg.get("level", "DEBUG").upper()
    file_enabled = log_cfg.get("file_enabled", True)
    file_path = log_cfg.get("file", "logs/mt5_streamer.log")

    log_path = Path(file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)  # ensure logs/ exists

    handlers = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        }
    }

    if file_enabled:
        handlers["file"] = {
            "class": "logging.FileHandler",
            "formatter": "standard",
            "filename": str(log_path),
            "mode": "a",
        }

    root_handlers = ["console"]
    if file_enabled:
        root_handlers.append("file")

    config = {
        "version": 1,
        "formatters": {
            "standard": {
                "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
            }
        },
        "handlers": handlers,
        "root": {
            "handlers": root_handlers,
            "level": level,
        },
    }
    dictConfig(config)


def main():
    print(">>> main() started")  # hard print, before logging

    parser = argparse.ArgumentParser(description="FX M1 MT5 streaming service")
    parser.add_argument(
        "--job",
        required=True,
        help="Name of streaming job defined in config/settings.yaml (e.g. 'ict_stream_m1')",
    )
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting streaming service with job '%s'...", args.job)

    cfg = _read_yaml()
    job_cfg = cfg["streaming"]["jobs"].get(args.job)
    if not job_cfg:
        logger.error("Job '%s' not found in settings.yaml", args.job)
        raise SystemExit(f"Job '{args.job}' not found in settings.yaml")
    if not job_cfg.get("enabled", True):
        logger.error("Job '%s' is disabled in settings.yaml", args.job)
        raise SystemExit(f"Job '{args.job}' is disabled in settings.yaml")

    logger.debug("Job config: %s", job_cfg)

    service = StreamerService(job_name=args.job)
    service.run_forever()


if __name__ == "__main__":
    main()
