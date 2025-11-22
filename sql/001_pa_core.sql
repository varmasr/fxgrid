-- 1) Store compact PA snapshots (per instrument, per decision time)
CREATE TABLE IF NOT EXISTS pa_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    instrument      TEXT NOT NULL,
    timestamp_utc   TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    tfs_context     JSONB NOT NULL,      -- H1/M15/M5/M1 context summary
    macro_context   JSONB NOT NULL,      -- events & risk flags
    created_at      TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pa_snapshots_inst_ts
ON pa_snapshots (instrument, timestamp_utc DESC);

-- 2) Trade plans produced by strategies (live or backtest)
CREATE TABLE IF NOT EXISTS trade_plans (
    id                  BIGSERIAL PRIMARY KEY,
    snapshot_id         BIGINT REFERENCES pa_snapshots(id) ON DELETE CASCADE,

    instrument          TEXT NOT NULL,
    direction           TEXT NOT NULL,         -- 'LONG'/'SHORT'
    setup_type          TEXT NOT NULL,         -- 'BR','LS','FVG_RETEST',...

    execution_tf        TEXT NOT NULL,         -- 'M1'/'M5'
    session             TEXT NOT NULL,         -- 'ASIA','LONDON','NY_OVERLAP','NY','AFTER'

    created_at          TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    valid_from          TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    valid_until         TIMESTAMP WITHOUT TIME ZONE NOT NULL,

    entry_min           NUMERIC(18, 8) NOT NULL,
    entry_max           NUMERIC(18, 8) NOT NULL,
    stop_loss           NUMERIC(18, 8) NOT NULL,
    tp1                 NUMERIC(18, 8),
    tp2                 NUMERIC(18, 8),
    rr1                 NUMERIC(10, 4),
    rr2                 NUMERIC(10, 4),

    strategy_name       TEXT NOT NULL,
    strategy_version    TEXT NOT NULL,
    confidence_score    NUMERIC(5, 2) DEFAULT 0.0,

    macro_risk_tag      TEXT,                  -- 'HIGH_EVENT_30M','CLEAR', etc.

    state               TEXT NOT NULL DEFAULT 'DRAFT',
    state_reason        TEXT,                  -- why INVALIDATED/CANCELLED

    metadata            JSONB,                 -- OB/FVG IDs, structure info
    llm_commentary      TEXT                   -- optional text commentary
);

CREATE INDEX IF NOT EXISTS idx_trade_plans_inst_state
ON trade_plans (instrument, state);

CREATE INDEX IF NOT EXISTS idx_trade_plans_valid_window
ON trade_plans (instrument, valid_from, valid_until);

-- 3) Backtest runs (aggregate)
CREATE TABLE IF NOT EXISTS backtest_runs (
    id               BIGSERIAL PRIMARY KEY,
    strategy_name    TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    instrument       TEXT NOT NULL,
    tf_execution     TEXT NOT NULL,   -- 'M1','M5'

    start_ts_utc     TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    end_ts_utc       TIMESTAMP WITHOUT TIME ZONE NOT NULL,

    initial_capital  NUMERIC(18, 2) NOT NULL,
    config           JSONB NOT NULL,  -- run config snapshot

    created_at       TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),

    total_trades     INTEGER,
    win_rate         NUMERIC(5, 2),
    gross_pnl        NUMERIC(18, 2),
    net_pnl          NUMERIC(18, 2),
    max_drawdown     NUMERIC(18, 2),
    sharpe           NUMERIC(10, 4)
);

CREATE INDEX IF NOT EXISTS idx_backtest_runs_inst_strategy
ON backtest_runs (instrument, strategy_name, strategy_version);

-- 4) Backtest trades (per trade)
CREATE TABLE IF NOT EXISTS backtest_trades (
    id                 BIGSERIAL PRIMARY KEY,
    run_id             BIGINT REFERENCES backtest_runs(id) ON DELETE CASCADE,

    instrument         TEXT NOT NULL,
    direction          TEXT NOT NULL,
    setup_type         TEXT NOT NULL,
    execution_tf       TEXT NOT NULL,

    entry_ts_utc       TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    exit_ts_utc        TIMESTAMP WITHOUT TIME ZONE NOT NULL,

    entry_price        NUMERIC(18, 8) NOT NULL,
    exit_price         NUMERIC(18, 8) NOT NULL,
    stop_loss          NUMERIC(18, 8),
    tp_price           NUMERIC(18, 8),

    size_lots          NUMERIC(18, 4) NOT NULL,
    gross_pnl          NUMERIC(18, 4) NOT NULL,
    net_pnl            NUMERIC(18, 4) NOT NULL,

    max_favorable_excursion NUMERIC(18, 4),
    max_adverse_excursion   NUMERIC(18, 4),

    trade_plan_data    JSONB,  -- serialized TradePlan
    pa_snapshot_data   JSONB   -- serialized PAContext/PASnapshot
);

CREATE INDEX IF NOT EXISTS idx_backtest_trades_run
ON backtest_trades (run_id);
