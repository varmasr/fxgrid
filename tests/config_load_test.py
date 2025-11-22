from pa_engine.config.loader import build_app_config

cfg = build_app_config()
print(cfg.database)
