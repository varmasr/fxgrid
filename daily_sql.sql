SHOW timezone;

SET timezone = 'UTC';

select * from market_data_m1 mdm 
where "timestamp" = '2025-10-29' order by "timestamp" desc;

select * from market_data_m1 mdm order by "timestamp" desc limit 10;

select * from live_market_data_m1 lmdm order by "timestamp" desc;

select * from live_market_data_m1 lmdm where instrument = 'USDJPY'
order by "timestamp" desc;

select * from macro_calendar_events mce order by datetime_utc desc;

select * from v_data_m1 where instrument = 'USDJPY' order by ts_utc desc;

select max(bid_high) from v_data_m1 where instrument = 'USDJPY' 
and ts_utc >= '2025-11-20' and "session"= "LONDON";

SELECT max(bid_high)
FROM v_data_m1
WHERE instrument='USDJPY'
  AND ts_utc >= '2025-11-20'
  AND ts_utc <  '2025-11-21'
  AND session='LONDON';
 
 SELECT *
FROM v_data_m1 v
WHERE instrument = 'USDJPY'
  AND ts_utc >= '2025-11-20'
  AND ts_utc < '2025-11-21'
  AND session = 'LONDON'
  AND bid_high = (
      SELECT MAX(bid_high)
      FROM v_data_m1 v2
      WHERE v2.instrument = v.instrument
        AND v2.ts_utc >= '2025-11-20'
        AND v2.ts_utc < '2025-11-21'
        AND v2.session = 'LONDON'
  );


 SELECT ts_utc, bid_open
FROM v_data_m1
WHERE instrument = 'USDJPY'
  AND ts_utc >= '2025-11-20 00:00:00'
  AND ts_utc <  '2025-11-21 00:00:00'
ORDER BY ts_utc
LIMIT 1;



SELECT ts_utc, bid_open
FROM v_data_m1
WHERE instrument = 'USDJPY'
  AND ts_utc >= '2025-11-20 00:00:00'
  AND ts_utc <  '2025-11-21 00:00:00'
ORDER BY ts_utc
LIMIT 1;





-----

-- INFORMATION SCHEMA 
SELECT table_name, column_name, data_type, numeric_precision, numeric_scale
FROM information_schema.columns 
WHERE table_name IN ('live_market_data_m1', 'market_data_m1','macro_calendar_events')
AND table_schema = 'public'
ORDER BY table_name, ordinal_position

-- Hypertable (if not already)
SELECT create_hypertable('live_market_data_m1', 'timestamp', if_not_exists => TRUE);

-- Unique constraint to make inserts idempotent
ALTER TABLE live_market_data_m1
  ADD CONSTRAINT live_market_data_m1_uniq UNIQUE (instrument, "timestamp");


delete  from live_market_data_m1 ;


-- UNIFIED VIEW
CREATE OR REPLACE VIEW v1_data_m1 AS
WITH params AS (
    SELECT
        (NOW() AT TIME ZONE 'UTC')::date AS today_utc
),
hist AS (
    SELECT
        m.instrument,
        (m.timestamp AT TIME ZONE 'UTC') AS ts_utc,
        m.bid_open,
        m.bid_high,
        m.bid_low,
        m.bid_close,
        m.ask_open,
        m.ask_high,
        m.ask_low,
        m.ask_close,
        m.volume::numeric    AS raw_volume,      -- real volume from history
        NULL::bigint         AS raw_tick_count,  -- no tick_count in hist
        'historical'::text   AS data_source
    FROM market_data_m1 m
    CROSS JOIN params p
    WHERE m.timestamp < p.today_utc          -- strictly before today (UTC)
),
live AS (
    SELECT
        l.instrument,
        (l.timestamp AT TIME ZONE 'UTC') AS ts_utc,
        l.bid_open,
        l.bid_high,
        l.bid_low,
        l.bid_close,
        l.ask_open,
        l.ask_high,
        l.ask_low,
        l.ask_close,
        l.volume::numeric    AS raw_volume,      -- often 0, but keep
        l.tick_count::bigint AS raw_tick_count,  -- live tick count
        'live'::text         AS data_source
    FROM live_market_data_m1 l
    CROSS JOIN params p
    WHERE l.timestamp >= p.today_utc         -- today’s candles from live
)
SELECT
    u.instrument,
    u.ts_utc,
    u.bid_open,
    u.bid_high,
    u.bid_low,
    u.bid_close,
    u.ask_open,
    u.ask_high,
    u.ask_low,
    u.ask_close,
    u.raw_volume,
    u.raw_tick_count,
    COALESCE(u.raw_tick_count::numeric, u.raw_volume) AS norm_volume,
    u.data_source,
    CASE
        WHEN u.ts_utc::time >= TIME '21:00' AND u.ts_utc::time < TIME '08:00'
            THEN 'ASIA'
        WHEN u.ts_utc::time >= TIME '08:00' AND u.ts_utc::time < TIME '13:00'
            THEN 'LONDON'
        WHEN u.ts_utc::time >= TIME '13:00' AND u.ts_utc::time < TIME '16:00'
            THEN 'NY_OVERLAP'
        WHEN u.ts_utc::time >= TIME '16:30' AND u.ts_utc::time < TIME '21:00'
            THEN 'NY'
        ELSE 'AFTER'
    END AS session
FROM (
    SELECT * FROM hist
    UNION ALL
    SELECT * FROM live
) AS u;


CREATE OR REPLACE VIEW v1_data_m1 AS
WITH params AS (
    SELECT
        (NOW() AT TIME ZONE 'UTC')::date AS today_utc
),
hist AS (
    SELECT
        m.instrument,
        (m.timestamp AT TIME ZONE 'UTC') AS ts_utc,
        m.bid_open,
        m.bid_high,
        m.bid_low,
        m.bid_close,
        m.ask_open,
        m.ask_high,
        m.ask_low,
        m.ask_close,
        m.volume::numeric    AS raw_volume,      -- real volume from history
        NULL::bigint         AS raw_tick_count,  -- no tick_count in hist
        'historical'::text   AS data_source
    FROM market_data_m1 m
    CROSS JOIN params p
    WHERE m.timestamp < p.today_utc          -- strictly before today (UTC)
),
live AS (
    SELECT
        l.instrument,
        (l.timestamp AT TIME ZONE 'UTC') AS ts_utc,
        l.bid_open,
        l.bid_high,
        l.bid_low,
        l.bid_close,
        l.ask_open,
        l.ask_high,
        l.ask_low,
        l.ask_close,
        l.volume::numeric    AS raw_volume,      -- often 0, but keep
        l.tick_count::bigint AS raw_tick_count,  -- live tick count
        'live'::text         AS data_source
    FROM live_market_data_m1 l
    CROSS JOIN params p
    WHERE l.timestamp >= p.today_utc         -- today’s candles from live
)
SELECT
    u.instrument,
    u.ts_utc,
    u.bid_open,
    u.bid_high,
    u.bid_low,
    u.bid_close,
    u.ask_open,
    u.ask_high,
    u.ask_low,
    u.ask_close,
    u.raw_volume,
    u.raw_tick_count,
    COALESCE(u.raw_tick_count::numeric, u.raw_volume) AS norm_volume,
    u.data_source
FROM (
    SELECT * FROM hist
    UNION ALL
    SELECT * FROM live
) AS u;


DROP VIEW IF EXISTS v1_data_m1 CASCADE;

select * from v1_data_m1 vdm order by ts_utc desc;

select * from live_market_data_m1 lmdm where instrument = 'USDJPY'
order by "timestamp" desc;


DROP VIEW IF EXISTS v_candles_m1_enriched;

DROP VIEW IF EXISTS v_data_m1_enriched;

CREATE OR REPLACE VIEW v_data_m1_enriched AS
SELECT
    c.instrument,
    c.ts_utc,
    c.bid_open,
    c.bid_high,
    c.bid_low,
    c.bid_close,
    c.ask_open,
    c.ask_high,
    c.ask_low,
    c.ask_close,
    c.raw_volume,
    c.raw_tick_count,
    c.norm_volume,
    c.data_source,
    c.session,
    e.ff_id,
    e.event_name,
    e.currency        AS event_currency,
    e.impact          AS event_impact,
    e.datetime_utc    AS event_time,
    CASE
        WHEN e.datetime_utc IS NOT NULL THEN TRUE
        ELSE FALSE
    END AS within_30m_event_window
FROM v1_data_m1 c
LEFT JOIN macro_calendar_events e
    ON e.datetime_utc BETWEEN c.ts_utc - INTERVAL '30 minutes'
                         AND c.ts_utc + INTERVAL '30 minutes';


   
select * from v_data_m1_enriched where instrument = 'USDJPY'
order by ts_utc desc limit 10;


-- Historical candles
CREATE UNIQUE INDEX IF NOT EXISTS ux_market_data_m1_inst_ts
ON market_data_m1 (instrument, "timestamp");




-- Live candles
CREATE UNIQUE INDEX IF NOT EXISTS ux_live_market_data_m1_inst_ts
ON live_market_data_m1 (instrument, "timestamp");


DROP MATERIALIZED VIEW IF EXISTS mv_data_m1_enriched;

CREATE MATERIALIZED VIEW mv_data_m1_enriched AS
SELECT
    c.instrument,
    c.ts_utc,
    c.bid_open,
    c.bid_high,
    c.bid_low,
    c.bid_close,
    c.ask_open,
    c.ask_high,
    c.ask_low,
    c.ask_close,
    c.raw_volume,
    c.raw_tick_count,
    c.norm_volume,
    c.data_source,
    c.session,
    e.ff_id,
    e.event_name,
    e.currency        AS event_currency,
    e.impact          AS event_impact,
    e.datetime_utc    AS event_time,
    CASE
        WHEN e.datetime_utc IS NOT NULL THEN TRUE
        ELSE FALSE
    END AS within_30m_event_window
FROM v1_data_m1 c
LEFT JOIN macro_calendar_events e
    ON e.datetime_utc BETWEEN c.ts_utc - INTERVAL '30 minutes'
                         AND c.ts_utc + INTERVAL '30 minutes';

-- 🔑 Composite index for fast per-instrument queries
CREATE INDEX IF NOT EXISTS idx_mv_data_m1_enriched_inst_ts
ON mv_data_m1_enriched (instrument, ts_utc DESC);

CREATE INDEX IF NOT EXISTS idx_market_data_m1_inst
ON market_data_m1 (instrument);

CREATE INDEX IF NOT EXISTS idx_live_market_data_m1_inst
ON live_market_data_m1 (instrument);

CREATE INDEX IF NOT EXISTS idx_market_data_m1_ts
ON market_data_m1 ("timestamp");

CREATE INDEX IF NOT EXISTS idx_live_market_data_m1_ts
ON live_market_data_m1 ("timestamp");

DROP MATERIALIZED VIEW IF EXISTS mv_data_m1;
DROP VIEW IF EXISTS mv_data_m1;

CREATE MATERIALIZED VIEW mv_data_m1 AS
WITH params AS (
    SELECT
        (NOW() AT TIME ZONE 'UTC')::date AS today_utc
),
hist AS (
    SELECT
        m.instrument,
        m.timestamp AS ts_utc,
        m.bid_open,
        m.bid_high,
        m.bid_low,
        m.bid_close,
        m.ask_open,
        m.ask_high,
        m.ask_low,
        m.ask_close,
        m.volume::numeric    AS raw_volume,
        NULL::bigint         AS raw_tick_count,
        'historical'::text   AS data_source
    FROM market_data_m1 m
    CROSS JOIN params p
    WHERE m.timestamp < p.today_utc
),
live AS (
    SELECT
        l.instrument,
        l.timestamp AS ts_utc,
        l.bid_open,
        l.bid_high,
        l.bid_low,
        l.bid_close,
        l.ask_open,
        l.ask_high,
        l.ask_low,
        l.ask_close,
        l.volume::numeric    AS raw_volume,
        l.tick_count::bigint AS raw_tick_count,
        'live'::text         AS data_source
    FROM live_market_data_m1 l
    CROSS JOIN params p
    WHERE l.timestamp >= p.today_utc
)
SELECT
    u.instrument,
    u.ts_utc,
    u.bid_open,
    u.bid_high,
    u.bid_low,
    u.bid_close,
    u.ask_open,
    u.ask_high,
    u.ask_low,
    u.ask_close,
    u.raw_volume,
    u.raw_tick_count,
    COALESCE(u.raw_tick_count::numeric, u.raw_volume) AS norm_volume,
    u.data_source,
    CASE
        WHEN u.ts_utc::time < TIME '08:00' THEN 'ASIA'
        WHEN u.ts_utc::time < TIME '13:00' THEN 'LONDON'
        WHEN u.ts_utc::time < TIME '16:30' THEN 'NY_OVERLAP'
        WHEN u.ts_utc::time < TIME '22:00' THEN 'NY'
        ELSE 'AFTER'
    END AS session
FROM (
    SELECT * FROM hist
    UNION ALL
    SELECT * FROM live
) AS u;

CREATE INDEX IF NOT EXISTS idx_mv_data_m1_inst_ts
ON mv_data_m1 (instrument, ts_utc DESC);

CREATE INDEX IF NOT EXISTS idx_mv_data_m1_ts
ON mv_data_m1 (ts_utc DESC);

CREATE INDEX IF NOT EXISTS idx_mv_data_m1_session
ON mv_data_m1 (session);

REFRESH MATERIALIZED VIEW CONCURRENTLY mv_data_m1;


SELECT instrument, ts_utc, COUNT(*) AS cnt
FROM mv_data_m1
GROUP BY instrument, ts_utc
HAVING COUNT(*) > 1
ORDER BY cnt DESC
LIMIT 20;

-- Drop any existing non-unique index on these cols (optional but cleaner)
DROP INDEX IF EXISTS idx_mv_data_m1_inst_ts;

-- Create the required UNIQUE index (no WHERE clause)
CREATE UNIQUE INDEX mv_data_m1_inst_ts_uid
ON mv_data_m1 (instrument, ts_utc);


-- 1) Store compact PA snapshots (per instrument, per decision time)
CREATE TABLE IF NOT EXISTS pa_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    instrument      TEXT NOT NULL,
    timestamp_utc   TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    tfs_context     JSONB NOT NULL,      -- H1/M15/M5/M1 context summary
    macro_context   JSONB NOT NULL,      -- events & risk flags
    created_at      TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

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


CREATE INDEX IF NOT EXISTS idx_pa_snapshots_inst_ts
ON pa_snapshots (instrument, timestamp_utc DESC);

CREATE INDEX IF NOT EXISTS idx_trade_plans_inst_state
ON trade_plans (instrument, state);

CREATE INDEX IF NOT EXISTS idx_trade_plans_valid_window
ON trade_plans (instrument, valid_from, valid_until);

DROP TABLE IF EXISTS backtest_runs CASCADE;

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

DROP TABLE IF EXISTS backtest_trades CASCADE;

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






SELECT *
FROM v_data_m1
WHERE instrument = 'USDJPY' 
ORDER BY ts_utc desc;
--LIMIT 100;



select * from v_data_m1 vcm where instrument = 'USDJPY'
order by ts_utc desc;

SELECT instrument, ts_utc, COUNT(*) AS cnt
FROM v_data_m1
GROUP BY instrument, ts_utc
HAVING COUNT(*) > 1
ORDER BY cnt DESC
LIMIT 100;



select * from macro_calendar_events mce  order by datetime_utc desc;


select * from live_market_data_m1 lmdm 
where instrument = 'XAUUSD'
order by "timestamp" 
desc;

-- delete from live data - use with caution
delete from market_data_m1
where timestamp >= '2025-11-01';

drop table backtest_results ;
-- INFORMATION SCHEMA
SELECT table_name, column_name, data_type, numeric_precision, numeric_scale
FROM information_schema.columns 
WHERE table_name IN ('live_market_data_m1', 'market_data_m1' , 'macro_calendar_events')
AND table_schema = 'public'
ORDER BY table_name, ordinal_position

-- Get the UNIFIED CANDLES INFO
SELECT COUNT(*) as total_candles, 
       MIN("timestamp") as oldest,
       MAX("timestamp") as newest
FROM get_unified_candles('USDJPY', 200);

SELECT COUNT(*) as total_candles, 
       MIN("timestamp") as oldest,
       MAX("timestamp") as newest
FROM get_unified_candles('USDJPY', 200);



-- COMPARE DUCASCOPY AND MT5 DATA - but before that load data in market_data_m1_validation table
WITH dukascopy_data AS (
    SELECT 
        timestamp,
        bid_close as dk_bid_close,
        ask_close as dk_ask_close,
        (ask_close - bid_close) as dk_spread
    FROM market_data_m1 
    WHERE instrument = 'USDJPY' 
    AND DATE(timestamp) = '2025-09-10'
    AND source = 'dukascopy'
),
mt5_data AS (
    SELECT 
        timestamp,
        bid_close as mt5_bid_close,
        ask_close as mt5_ask_close,
        (ask_close - bid_close) as mt5_spread
    FROM market_data_m1_validation 
    WHERE instrument = 'USDJPY' 
    AND DATE(timestamp) = '2025-09-10'
    AND source = 'mt5_demo'
)
SELECT 
    d.timestamp,
    d.dk_bid_close,
    m.mt5_bid_close,
    ABS(d.dk_bid_close - m.mt5_bid_close) as price_diff_pips,
    ((d.dk_bid_close - m.mt5_bid_close) / d.dk_bid_close * 100) as price_diff_percent,
    d.dk_spread,
    m.mt5_spread,
    ABS(d.dk_spread - m.mt5_spread) as spread_diff
FROM dukascopy_data d
INNER JOIN mt5_data m ON d.timestamp = m.timestamp
ORDER BY d.timestamp;


-- This should now return 0 (UTC) instead of 5.5 (IST)
SELECT 
    timestamp,
    EXTRACT(timezone FROM timestamp) / 3600 as hours_from_utc
FROM market_data_m1  lmdm WHERE instrument = 'USDJPY' order by timestamp desc;

-- market data  grouped by instrument
SELECT 
    instrument,
    COUNT(*) as total_bars,
    MIN(timestamp) as earliest,
    MAX(timestamp) as latest,
    MIN(bid_close) as min_price,
    MAX(bid_close) as max_price
FROM market_data_m1 
WHERE instrument = 'USDJPY'
GROUP BY instrument;

-- live data grouped by instrument
SELECT 
    instrument,
    COUNT(*) as total_bars,
    MIN(timestamp) as earliest,
    MAX(timestamp) as latest,
    MIN(bid_close) as min_price,
    MAX(bid_close) as max_price
FROM live_market_data_m1 lmdm 
--WHERE instrument = 'USDJPY'
GROUP BY instrument;


-- Check all timezone-related settings
SELECT name, setting FROM pg_settings WHERE name LIKE '%timezone%';

SELECT NOW() as server_time, timezone('UTC', NOW()) as explicit_utc;


-- Table schema info 
 SELECT table_schema, table_name
FROM information_schema.views
WHERE table_schema IN ('public');




select * from backtest_runs;


-- sanity checks
--Date range present (USDJPY)
SELECT
  MIN(ts_utc) AS first_ts,
  MAX(ts_utc) AS last_ts,
  COUNT(*)    AS rows
FROM v_candles_m1
WHERE instrument = 'USDJPY';

-- missing m1 timestamps
WITH series AS (
  SELECT gs AS ts_utc
  FROM generate_series(
         (SELECT date_trunc('minute', MIN(ts_utc)) FROM v_candles_m1 WHERE instrument='USDJPY'),
         (SELECT date_trunc('minute', MAX(ts_utc)) FROM v_candles_m1 WHERE instrument='USDJPY'),
         INTERVAL '1 minute'
       ) AS gs
  WHERE EXTRACT(ISODOW FROM gs) BETWEEN 1 AND 5   -- Mon..Fri
),
seen AS (
  SELECT DISTINCT date_trunc('minute', ts_utc) AS ts_utc
  FROM v_candles_m1
  WHERE instrument='USDJPY'
)
SELECT s.ts_utc
FROM series s
LEFT JOIN seen  v ON v.ts_utc = s.ts_utc
WHERE v.ts_utc IS NULL
ORDER BY s.ts_utc
LIMIT 1000;

-- count how many minutes are missing per day/week:
WITH series AS (
  SELECT gs AS ts_utc
  FROM generate_series(
           (SELECT date_trunc('minute', MIN(ts_utc)) FROM v_candles_m1 WHERE instrument='USDJPY'),
           (SELECT date_trunc('minute', MAX(ts_utc)) FROM v_candles_m1 WHERE instrument='USDJPY'),
           INTERVAL '1 minute'
       ) gs
  WHERE EXTRACT(ISODOW FROM gs) BETWEEN 1 AND 5
),
seen AS (
  SELECT date_trunc('minute', ts_utc) ts_utc
  FROM v_candles_m1
  WHERE instrument='USDJPY'
)
SELECT date_trunc('day', s.ts_utc) AS day,
       COUNT(*) FILTER (WHERE v.ts_utc IS NULL) AS missing_minutes
FROM series s
LEFT JOIN seen v ON s.ts_utc = v.ts_utc
GROUP BY 1
ORDER BY 1;


--Quick volume/price sanity (catch bad spikes/zeros)
SELECT
  SUM(CASE WHEN volume < 0 THEN 1 ELSE 0 END) AS neg_vol,
  SUM(CASE WHEN bid_high < bid_low THEN 1 ELSE 0 END) AS bad_hilo,
  SUM(CASE WHEN spread_close < 0 THEN 1 ELSE 0 END) AS neg_spread
FROM v_candles_m1
WHERE instrument='USDJPY';

-- Macro events joined to candles (windowed)
SELECT c.ts_utc, c.bid_close, m.event_name, m.impact, m.currency
FROM v_candles_m1 c
LEFT JOIN macro_calendar_events m
  ON m.datetime_utc BETWEEN c.ts_utc - INTERVAL '30 minutes'
                 AND c.ts_utc + INTERVAL '30 minutes'
WHERE c.instrument='USDJPY'
  AND c.ts_utc >= NOW() AT TIME ZONE 'UTC' - INTERVAL '2 days'
ORDER BY c.ts_utc
LIMIT 500;

SELECT schemaname AS view_schema,
       viewname   AS view_name,
       definition AS view_sql
FROM pg_views
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY view_schema, view_name;


 WITH bounds AS (
         SELECT date_trunc('day'::text, (now() AT TIME ZONE 'utc'::text)) AS today_start_utc
        )
 SELECT m.instrument,
    m."timestamp" AS ts_utc,
    m.bid_open,
    m.bid_high,
    m.bid_low,
    m.bid_close,
    m.ask_open,
    m.ask_high,
    m.ask_low,
    m.ask_close,
    (m.ask_close - m.bid_close) AS spread_close,
    (m.volume)::numeric AS volume,
    NULL::integer AS tick_count,
    'hist'::text AS source,
    NULL::text AS data_source_type,
    NULL::numeric AS data_quality_score,
    NULL::integer AS processing_latency_ms,
    m.created_at AS created_at_utc,
    NULL::text AS created_by,
    m.is_validated
   FROM market_data_m1 m,
    bounds b
  WHERE (m."timestamp" < b.today_start_utc)
UNION ALL
 SELECT l.instrument,
    l."timestamp" AS ts_utc,
    l.bid_open,
    l.bid_high,
    l.bid_low,
    l.bid_close,
    l.ask_open,
    l.ask_high,
    l.ask_low,
    l.ask_close,
    (l.ask_close - l.bid_close) AS spread_close,
    (l.volume)::numeric AS volume,
    l.tick_count,
    'live'::text AS source,
    NULL::text AS data_source_type,
    NULL::numeric AS data_quality_score,
    NULL::integer AS processing_latency_ms,
    l.received_at AS created_at_utc,
    NULL::text AS created_by,
    NULL::boolean AS is_validated
   FROM live_market_data_m1 l,
    bounds b
  WHERE (l."timestamp" >= b.today_start_utc);
 
 
-- APPLY CORE SCHEMA

select * from accounts;
CREATE TABLE IF NOT EXISTS accounts (
  account_id      TEXT PRIMARY KEY,
  name            TEXT NOT NULL,
  prop_firm       TEXT NOT NULL,
  base_currency   TEXT NOT NULL DEFAULT 'USD',
  config_json     JSONB NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

select * from prop_firm_rules;
CREATE TABLE IF NOT EXISTS prop_firm_rules (
  prop_firm       TEXT PRIMARY KEY,
  rules_json      JSONB NOT NULL,  -- daily loss, max loss, news filter, allowed symbols, etc.
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- Strategy registry & deployments
select * from strategies;
CREATE TABLE IF NOT EXISTS strategies (
  strategy_name   TEXT PRIMARY KEY,
  group_name      TEXT,
  yaml_text       TEXT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

select * from deployments;
CREATE TABLE IF NOT EXISTS deployments (
  deployment_id   UUID PRIMARY KEY,
  strategy_name   TEXT REFERENCES strategies(strategy_name),
  account_id      TEXT REFERENCES accounts(account_id),
  params_json     JSONB NOT NULL,
  status          TEXT NOT NULL CHECK(status IN ('PENDING','ACTIVE','PAUSED','STOPPED')),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

select * from backtest_runs;
-- Backtests
CREATE TABLE IF NOT EXISTS backtest_runs (
  run_id          UUID PRIMARY KEY,
  strategy_name   TEXT NOT NULL,
  account_id      TEXT,
  symbol          TEXT NOT NULL,
  timeframe       TEXT NOT NULL,
  params_json     JSONB NOT NULL,
  data_window     TSRANGE,
  started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at     TIMESTAMPTZ
);

select * from backtest_trades;
CREATE TABLE IF NOT EXISTS backtest_trades (
  trade_id        UUID PRIMARY KEY,
  run_id          UUID REFERENCES backtest_runs(run_id) ON DELETE CASCADE,
  symbol          TEXT,
  side            TEXT CHECK (side IN ('LONG','SHORT')),
  entry_time      TIMESTAMPTZ,
  exit_time       TIMESTAMPTZ,
  entry_price     DOUBLE PRECISION,
  exit_price      DOUBLE PRECISION,
  sl_price        DOUBLE PRECISION,
  tp_price        DOUBLE PRECISION,
  size_lots       DOUBLE PRECISION,
  gross_pnl       DOUBLE PRECISION,
  fees            DOUBLE PRECISION,
  net_pnl         DOUBLE PRECISION,
  bars_held       INT,
  reason_json     JSONB
);

select * from backtest_results;
CREATE TABLE IF NOT EXISTS backtest_results (
  run_id          UUID PRIMARY KEY REFERENCES backtest_runs(run_id) ON DELETE CASCADE,
  total_trades    INT,
  win_rate        DOUBLE PRECISION,
  avg_r           DOUBLE PRECISION,
  expectancy_r    DOUBLE PRECISION,
  sharpe          DOUBLE PRECISION,
  sortino         DOUBLE PRECISION,
  max_dd_pct      DOUBLE PRECISION,
  pf_ratio        DOUBLE PRECISION,
  equity_png      TEXT
);


-- Live signals + execution tracking

select * from live_signals;
CREATE TABLE IF NOT EXISTS live_signals (
  signal_id       UUID PRIMARY KEY,
  deployment_id   UUID REFERENCES deployments(deployment_id),
  symbol          TEXT NOT NULL,
  timeframe       TEXT NOT NULL,
  side            TEXT CHECK (side IN ('LONG','SHORT')),
  ts_utc          TIMESTAMPTZ NOT NULL,
  entry_price     DOUBLE PRECISION,
  sl_price        DOUBLE PRECISION,
  tp_price        DOUBLE PRECISION,
  status          TEXT NOT NULL CHECK(status IN ('OPEN','EXIT','CANCELLED','MISSED','EXPIRED')),
  meta_json       JSONB
);

select * from  live_executions;
CREATE TABLE IF NOT EXISTS live_executions (
  exec_id         UUID PRIMARY KEY,
  signal_id       UUID REFERENCES live_signals(signal_id),
  broker_order_id TEXT,
  status          TEXT CHECK(status IN ('SUBMITTED','FILLED','REJECTED','CANCELLED')),
  filled_price    DOUBLE PRECISION,
  qty_lots        DOUBLE PRECISION,
  fees            DOUBLE PRECISION,
  pnl             DOUBLE PRECISION,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-------------------- ----- RL / LLM BASED SCHEMAS ---------------------------------------------------

CREATE OR REPLACE VIEW v_m1_base AS
SELECT
  instrument,
  ts_utc::timestamptz                AS ts,
  bid_open::double precision,
  bid_high::double precision,
  bid_low::double precision,
  bid_close::double precision,
  ask_open::double precision,
  ask_high::double precision,
  ask_low::double precision,
  ask_close::double precision,
  volume::bigint,
  tick_count::bigint,
  source::text,
  created_at_utc::timestamptz,
  is_validated
FROM v_candles_m1;

SELECT * FROM v_m1_base WHERE instrument='USDJPY' ORDER BY ts DESC LIMIT 5;


CREATE MATERIALIZED VIEW IF NOT EXISTS mv_m5 AS
SELECT
  instrument,
  time_bucket('5 minutes', ts) AS bucket,
  first(bid_open, ts)  AS bid_open,
  max(bid_high)        AS bid_high,
  min(bid_low)         AS bid_low,
  last(bid_close, ts)  AS bid_close,
  first(ask_open, ts)  AS ask_open,
  max(ask_high)        AS ask_high,
  min(ask_low)         AS ask_low,
  last(ask_close, ts)  AS ask_close,
  sum(volume)          AS volume,
  sum(tick_count)      AS tick_count
FROM v_m1_base
GROUP BY instrument, bucket;

-- On demand:
REFRESH MATERIALIZED VIEW mv_m5;

CREATE UNIQUE INDEX mv_m5_uq ON mv_m5 (instrument, bucket);

REFRESH MATERIALIZED VIEW CONCURRENTLY mv_m5;



CREATE MATERIALIZED VIEW IF NOT EXISTS event_windows AS
SELECT
  ff_id,
  currency,
  impact,
  event_name,
  datetime_utc::timestamptz,
  (datetime_utc::timestamptz - INTERVAL '60 min') AS pre_60_start,
  (datetime_utc::timestamptz + INTERVAL '60 min') AS post_60_end
FROM macro_calendar_events mce 
WHERE currency IN ('USD','JPY');


select * from macro_calendar_events mce limit 10;



CREATE OR REPLACE VIEW v_m1_evented AS
SELECT
  v.*,
  e.ff_id,
  (e.datetime_utc - v.ts)                                AS delta_to_event,
  (v.ts BETWEEN e.pre_60_start AND e.post_60_end)        AS in_event_window
FROM v_m1_base v
LEFT JOIN LATERAL (
  SELECT
    ff_id,
    datetime_utc,
    pre_60_start,
    post_60_end
  FROM event_windows
  WHERE datetime_utc BETWEEN v.ts - INTERVAL '24 hours' AND v.ts + INTERVAL '24 hours'
  ORDER BY ABS(EXTRACT(EPOCH FROM (datetime_utc - v.ts)))  -- <- key change
  LIMIT 1
) e ON TRUE;


CREATE INDEX IF NOT EXISTS event_windows_dt_idx ON event_windows (datetime_utc);

-- Should return rows without error
SELECT * FROM v_m1_evented
WHERE instrument='USDJPY' AND in_event_window
ORDER BY ts DESC
LIMIT 5;

-- Inspect sign of delta (negative = event in the past)
SELECT ts, ff_id, delta_to_event
FROM v_m1_evented
WHERE instrument='USDJPY'
ORDER BY ABS(EXTRACT(EPOCH FROM delta_to_event))
LIMIT 10;


SELECT * FROM v_m1_evented
WHERE instrument='USDJPY' AND in_event_window
ORDER BY ts DESC LIMIT 5;

CREATE TABLE IF NOT EXISTS features_m1 (
  instrument text,
  ts timestamptz,
  mid_close     double precision,   -- (bid_close+ask_close)/2
  spread_pips   double precision,   -- (ask_close-bid_close)*100 (adjust for 3/2 decimals as needed)
  ret1          double precision,   -- log return of mid
  rv5           double precision,   -- rolling std of ret1 over 5 bars
  tr            double precision,   -- true range proxy using mid_prev
  tokyo boolean, london boolean, ny boolean,
  tokyo_fix_window boolean, wmr_fix_window boolean, gotobi boolean,
  minutes_to_event integer,
  PRIMARY KEY (instrument, ts)
);

SELECT create_hypertable('features_m1','ts', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS features_m1_idx ON features_m1 (instrument, ts DESC);


INSERT INTO features_m1 (
  instrument, ts, mid_close, spread_pips, ret1, rv5, tr,
  tokyo, london, ny, tokyo_fix_window, wmr_fix_window, gotobi, minutes_to_event
)
SELECT
  sub.instrument,
  sub.ts,
  sub.mid_close,
  sub.spread_pips,
  sub.ret1,
  /* rolling 5-bar stddev of ret1 */
  stddev_samp(sub.ret1) OVER (
    PARTITION BY sub.instrument ORDER BY sub.ts
    ROWS BETWEEN 5 PRECEDING AND CURRENT ROW
  ) AS rv5,
  /* true-range proxy using mid_prev */
  GREATEST(
    sub.hi_all - sub.lo_all,
    ABS(sub.hi_all - COALESCE(sub.mid_prev, sub.mid_close)),
    ABS(COALESCE(sub.mid_prev, sub.mid_close) - sub.lo_all)
  ) AS tr,
  /* Sessions (DST-aware via AT TIME ZONE) */
  (EXTRACT(HOUR FROM (sub.ts AT TIME ZONE 'Asia/Tokyo'))       BETWEEN 9 AND 17) AS tokyo,
  (EXTRACT(HOUR FROM (sub.ts AT TIME ZONE 'Europe/London'))    BETWEEN 8 AND 16) AS london,
  (EXTRACT(HOUR FROM (sub.ts AT TIME ZONE 'America/New_York')) BETWEEN 9 AND 16) AS ny,
  /* Fix windows: Tokyo 09:55 ±5m, WMR 16:00 London ±5m */
  (
    EXTRACT(HOUR   FROM (sub.ts AT TIME ZONE 'Asia/Tokyo')) = 9 AND
    EXTRACT(MINUTE FROM (sub.ts AT TIME ZONE 'Asia/Tokyo')) BETWEEN 50 AND 59
  ) AS tokyo_fix_window,
  (
      (EXTRACT(HOUR FROM (sub.ts AT TIME ZONE 'Europe/London')) = 15 AND
       EXTRACT(MINUTE FROM (sub.ts AT TIME ZONE 'Europe/London')) BETWEEN 55 AND 59)
   OR (EXTRACT(HOUR FROM (sub.ts AT TIME ZONE 'Europe/London')) = 16 AND
       EXTRACT(MINUTE FROM (sub.ts AT TIME ZONE 'Europe/London')) BETWEEN 0 AND 4)
  ) AS wmr_fix_window,
  /* Gotobi (Tokyo calendar day 5,10,15,20,25,30) */
  (EXTRACT(DAY FROM (sub.ts AT TIME ZONE 'Asia/Tokyo')) IN (5,10,15,20,25,30)) AS gotobi,
  /* Minutes to nearest USD/JPY macro event */
  (
    SELECT ROUND(EXTRACT(EPOCH FROM (ew.datetime_utc - sub.ts))/60.0)::int
    FROM event_windows ew
    WHERE ew.datetime_utc BETWEEN sub.ts - INTERVAL '24 hours' AND sub.ts + INTERVAL '24 hours'
      AND ew.currency IN ('USD','JPY')
    ORDER BY ABS(EXTRACT(EPOCH FROM (ew.datetime_utc - sub.ts)))
    LIMIT 1
  ) AS minutes_to_event
FROM (
  SELECT
    v.instrument,
    v.ts,
    (v.bid_close + v.ask_close)/2.0              AS mid_close,
    (v.ask_close - v.bid_close)*100.0            AS spread_pips,   -- USDJPY pip ≈ 0.01
    LAG((v.bid_close + v.ask_close)/2.0)
      OVER (PARTITION BY v.instrument ORDER BY v.ts) AS mid_prev,
    GREATEST(v.bid_high, v.ask_high)             AS hi_all,
    LEAST(v.bid_low,  v.ask_low )                AS lo_all,
    CASE
      WHEN LAG((v.bid_close + v.ask_close)/2.0)
           OVER (PARTITION BY v.instrument ORDER BY v.ts) IS NULL
        OR LAG((v.bid_close + v.ask_close)/2.0)
           OVER (PARTITION BY v.instrument ORDER BY v.ts) = 0
      THEN 0
      ELSE LN( ((v.bid_close + v.ask_close)/2.0) /
               LAG((v.bid_close + v.ask_close)/2.0)
               OVER (PARTITION BY v.instrument ORDER BY v.ts) )
    END AS ret1
  FROM v_m1_base v
  WHERE v.instrument = 'USDJPY'
) AS sub
ON CONFLICT (instrument, ts) DO NOTHING;



SELECT * FROM features_m1
WHERE instrument='USDJPY'
ORDER BY ts DESC
LIMIT 10;

SELECT ts, tokyo, london, ny, tokyo_fix_window, wmr_fix_window, gotobi
FROM features_m1
WHERE instrument='USDJPY'
ORDER BY ts DESC
LIMIT 2000;


CREATE TABLE IF NOT EXISTS labels_m1 (
  instrument text,
  ts timestamptz,
  tb_horizon text,          -- '5m'|'15m'|'60m'
  y_primary smallint,       -- +1 TP first / -1 SL first / 0 timeout
  y_meta    smallint,       -- 1 tradeable / 0 not
  tp_pips numeric, sl_pips numeric,
  max_hold interval,
  embargo_before interval, embargo_after interval,
  PRIMARY KEY (instrument, ts, tb_horizon)
);
SELECT create_hypertable('labels_m1','ts', if_not_exists => TRUE);


SELECT * FROM labels_m1
WHERE instrument='USDJPY';

CREATE OR REPLACE VIEW v_train_pack AS
SELECT f.*, l.tb_horizon, l.y_primary, l.y_meta
FROM   features_m1 f
JOIN   labels_m1   l USING (instrument, ts)
WHERE  instrument='USDJPY'
  AND  COALESCE(ABS(minutes_to_event), 9999) > 30    -- news embargo ±30m
  AND  NOT tokyo_fix_window
  AND  NOT wmr_fix_window;

 SELECT COUNT(*) FROM v_train_pack;


CREATE TABLE IF NOT EXISTS signals_shadow (
  ts timestamptz, instrument text, model_version text,
  horizon text, p_tp_gt_sl double precision, conf_width double precision,
  features_hash text,
  PRIMARY KEY (instrument, ts, horizon)
);

CREATE TABLE IF NOT EXISTS plans_shadow (
  plan_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ts timestamptz, instrument text, model_version text, horizon text,
  side text, entry double precision, sl double precision, tp double precision,
  size_lots double precision, tif text,
  checks_passed text[], rationale text
);

CREATE TABLE IF NOT EXISTS fills_shadow (
  plan_id uuid, child_id uuid DEFAULT gen_random_uuid(),
  ts timestamptz, side text, px double precision, qty double precision,
  slippage double precision, status text
);

CREATE TABLE IF NOT EXISTS episodes_shadow (
  plan_id uuid PRIMARY KEY,
  features_hash text, risk_snapshot jsonb,
  pnl double precision, mae double precision, mfe double precision,
  rule_breaches jsonb
);



-- Show same rows in UTC to confirm sessions line up
SELECT ts AT TIME ZONE 'UTC' AS ts_utc, ny, london, tokyo
FROM features_m1
WHERE instrument='USDJPY'
ORDER BY ts DESC LIMIT 10;

-- Convert rv5 to pip-vol per bar (just for inspection)
SELECT ts, mid_close, rv5,
       ROUND(100 * mid_close * rv5, 2) AS rv5_pips
FROM features_m1
WHERE instrument='USDJPY'
ORDER BY ts DESC LIMIT 10;

-- Make an explicit event-window flag using minutes_to_event
SELECT ts, minutes_to_event,
       (ABS(minutes_to_event) <= 30) AS in_event_±30m
FROM features_m1
WHERE instrument='USDJPY'
ORDER BY ts DESC LIMIT 20;


SELECT tb_horizon, COUNT(*) 
FROM labels_m1 WHERE instrument='USDJPY'
GROUP BY 1 ORDER BY 1;

SELECT l.ts, l.tb_horizon, l.y_primary, l.tp_pips, l.sl_pips, f.mid_close
FROM labels_m1 l JOIN features_m1 f USING (instrument, ts)
WHERE instrument='USDJPY'
ORDER BY ts asc LIMIT 200;


SELECT l.ts, l.tb_horizon, l.y_primary, l.tp_pips, l.sl_pips, f.mid_close
FROM labels_m1 l JOIN features_m1 f USING (instrument, ts)
WHERE instrument='USDJPY'
ORDER BY ts DESC LIMIT 20;


CREATE OR REPLACE VIEW v_train_pack_train AS
SELECT * FROM v_train_pack
WHERE instrument='USDJPY'
  AND ts BETWEEN '2022-01-01' AND '2024-12-31';
 
 
-- Dev/CV (feature work, hyperparam search)
CREATE OR REPLACE VIEW v_train_pack_train AS
SELECT * FROM v_train_pack
WHERE instrument='USDJPY'
  AND ts BETWEEN '2022-01-01' AND '2024-12-31';

-- OOS validation (sanity-check family choice)
CREATE OR REPLACE VIEW v_train_pack_val AS
SELECT * FROM v_train_pack
WHERE instrument='USDJPY'
  AND ts BETWEEN '2025-01-01' AND '2025-05-31';

-- Final holdout (touch only once at the end)
CREATE OR REPLACE VIEW v_train_pack_holdout AS
SELECT * FROM v_train_pack
WHERE instrument='USDJPY'
  AND ts BETWEEN '2025-06-01' AND '2025-09-26';

 
-- Make sure the training slice has rows
SELECT COUNT(*) FROM v_train_pack_train WHERE tb_horizon='15m' AND instrument='USDJPY';

-- See label balance (non-timeouts only; we dropped timeouts in the script)
SELECT y_primary, COUNT(*)
FROM v_train_pack_train
WHERE instrument='USDJPY' AND tb_horizon='15m' AND y_primary<>0
GROUP BY 1 ORDER BY 1;


CREATE OR REPLACE VIEW v_train_pack AS
SELECT
  f.*,
  l.tb_horizon,
  l.y_primary,
  l.y_meta,
  l.tp_pips,
  l.sl_pips,
  l.max_hold
FROM features_m1 f
JOIN labels_m1   l USING (instrument, ts)
WHERE instrument='USDJPY'                             -- keep or remove for multi-symbol
  AND COALESCE(ABS(minutes_to_event), 9999) > 30      -- news embargo ±30m
  AND NOT tokyo_fix_window
  AND NOT wmr_fix_window;
 
 
 -- Confirm the columns exist now
SELECT ts, tb_horizon, y_primary, tp_pips, sl_pips
FROM v_train_pack
WHERE instrument='USDJPY' AND tb_horizon='15m'
ORDER BY ts DESC
LIMIT 5;


-- TRAIN
CREATE OR REPLACE VIEW v_train_pack_train AS
SELECT *
FROM v_train_pack
WHERE instrument='USDJPY'
  AND ts BETWEEN '2022-01-01' AND '2024-12-31';

-- VALIDATION
CREATE OR REPLACE VIEW v_train_pack_val AS
SELECT *
FROM v_train_pack
WHERE instrument='USDJPY'
  AND ts BETWEEN '2025-01-01' AND '2025-05-31';

-- HOLDOUT
CREATE OR REPLACE VIEW v_train_pack_holdout AS
SELECT *
FROM v_train_pack
WHERE instrument='USDJPY'
  AND ts BETWEEN '2025-06-01' AND '2025-09-26';
 
 
 SELECT column_name
FROM information_schema.columns
WHERE table_name='v_train_pack_train'
ORDER BY ordinal_position;

-- and a quick peek:
SELECT ts, tb_horizon, y_primary, tp_pips, sl_pips
FROM v_train_pack_train
WHERE tb_horizon='15m'
ORDER BY ts DESC
LIMIT 5;



-- UUID helper (one of these two is fine)
CREATE EXTENSION IF NOT EXISTS pgcrypto;         -- gen_random_uuid()
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- uuid_generate_v4()

-- 1) Signals produced by the model
CREATE TABLE IF NOT EXISTS signals_shadow (
  ts timestamptz NOT NULL,
  instrument text NOT NULL,
  model_version text NOT NULL,
  horizon text NOT NULL,
  p_tp_gt_sl double precision NOT NULL,
  conf_width double precision,
  features_hash text,
  PRIMARY KEY (instrument, ts, horizon)
);
CREATE INDEX IF NOT EXISTS signals_shadow_ts_idx ON signals_shadow (ts DESC);

-- 2) Trade plans (what we intend to do)
CREATE TABLE IF NOT EXISTS plans_shadow (
  plan_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),     -- or uuid_generate_v4()
  ts timestamptz NOT NULL,
  instrument text NOT NULL,
  model_version text NOT NULL,
  horizon text NOT NULL,
  side text NOT NULL CHECK (side IN ('long','short')),
  entry double precision NOT NULL,
  sl double precision NOT NULL,
  tp double precision NOT NULL,
  size_lots double precision,
  tif text,
  checks_passed text[],
  rationale text
);
CREATE INDEX IF NOT EXISTS plans_shadow_ts_idx    ON plans_shadow (ts DESC);
CREATE INDEX IF NOT EXISTS plans_shadow_instr_idx ON plans_shadow (instrument, ts DESC);

-- 3) Fills (simulated or real executions)
CREATE TABLE IF NOT EXISTS fills_shadow (
  plan_id uuid NOT NULL REFERENCES plans_shadow(plan_id) ON DELETE CASCADE,
  child_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),   -- per-fill id
  ts timestamptz NOT NULL,
  side text NOT NULL,
  px double precision NOT NULL,
  qty double precision NOT NULL,
  slippage double precision,
  status text NOT NULL
);
CREATE INDEX IF NOT EXISTS fills_shadow_plan_idx ON fills_shadow (plan_id);

-- 4) Episode summary (PnL, excursions, breaches)
CREATE TABLE IF NOT EXISTS episodes_shadow (
  plan_id uuid PRIMARY KEY REFERENCES plans_shadow(plan_id) ON DELETE CASCADE,
  features_hash text,
  risk_snapshot jsonb,
  pnl double precision,
  mae double precision,
  mfe double precision,
  rule_breaches jsonb,
  created_at timestamptz DEFAULT now()
);


SELECT * FROM signals_shadow ORDER BY ts DESC LIMIT 5;
SELECT ts, side, entry, sl, tp, rationale
FROM plans_shadow
ORDER BY ts asc LIMIT 100;



WITH w AS (
  SELECT * FROM features_m1
  WHERE instrument='USDJPY'
    AND ts BETWEEN '2025-09-05 06:00+00' AND '2025-09-05 18:00+00'
)
SELECT COUNT(*) AS n_bars,
       SUM( (ABS(minutes_to_event) <= 30)::int ) AS n_event_±30m,
       SUM( tokyo_fix_window::int )               AS n_tokyo_fix,
       SUM( wmr_fix_window::int )                 AS n_wmr_fix
FROM w;


-- Delete a single replay batch (plans cascade to fills & episodes)

select * from plans_shadow;
DELETE FROM plans_shadow WHERE run_id = '0b3e8c8e-09fb-4d7a-9b67-6f3d0f2dfe66';

-- Optionally also clear signals from that run (if you added run_id to signals)
select * from signals_shadow ss ;
DELETE FROM signals_shadow WHERE run_id = '0b3e8c8e-09fb-4d7a-9b67-6f3d0f2dfe66';

-- INFORMATION SCHEMA
SELECT table_name, column_name, data_type, numeric_precision, numeric_scale
FROM information_schema.columns 
WHERE table_name IN ('signals_shadow', 'plans_shadow')
AND table_schema = 'public'
ORDER BY table_name, ordinal_position;


ALTER TABLE signals_shadow ADD COLUMN IF NOT EXISTS run_id uuid;
ALTER TABLE plans_shadow   ADD COLUMN IF NOT EXISTS run_id uuid;

CREATE INDEX IF NOT EXISTS signals_shadow_run_idx ON signals_shadow(run_id);
CREATE INDEX IF NOT EXISTS plans_shadow_run_idx   ON plans_shadow(run_id);

-- delete plans for that batch (cascades to fills/episodes if you set FK ON DELETE CASCADE)
delete FROM plans_shadow;

-- optional: also clear signals tagged with that run
DELETE from signals_shadow;


select * from features_m1 fm ;

-----------------------------

SELECT table_name, column_name, data_type, numeric_precision, numeric_scale
FROM information_schema.columns 
-- WHERE table_name IN ('signals_shadow', 'plans_shadow')
where table_schema = 'public'
ORDER BY table_name, ordinal_position;

-- Table schema info 
 SELECT table_schema, table_name
FROM information_schema.views
WHERE table_schema IN ('public');

 SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema IN ('public');

select * from labels_m1;

select * from v_candles_m1 vcm  order by ts_utc desc;

SELECT schemaname AS view_schema,
       viewname   AS view_name,
       definition AS view_sql
FROM pg_views
WHERE schemaname = 'public'     -- change to your schema
ORDER BY view_name;

select * from v_candles_m1 vcm;
 
-- Add order/TIF fields (safe add)
ALTER TABLE plans_shadow
  ADD COLUMN IF NOT EXISTS order_type TEXT,
  ADD COLUMN IF NOT EXISTS tif_mode   TEXT,
  ADD COLUMN IF NOT EXISTS tif_expire_bars INTEGER,
  ADD COLUMN IF NOT EXISTS limit_offset_pips DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS stop_offset_pips  DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS max_slippage_pips DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS spread_cap_pips   DOUBLE PRECISION;
 
 ALTER TABLE replay_trades_shadow
  ADD COLUMN IF NOT EXISTS exit_reason TEXT,
  ADD COLUMN IF NOT EXISTS both_hit_same_bar BOOLEAN,
  ADD COLUMN IF NOT EXISTS horizon_min INTEGER,
  ADD COLUMN IF NOT EXISTS expected_r DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS prob_win DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS rr DOUBLE PRECISION;




-- Trades (results of evaluation)
CREATE TABLE IF NOT EXISTS replay_trades_shadow (
  trade_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id   UUID NOT NULL,
  plan_id  UUID NOT NULL REFERENCES plans_shadow(plan_id) ON DELETE CASCADE,
  instrument TEXT NOT NULL,
  side    TEXT CHECK (side IN ('long','short')),
  entry_ts TIMESTAMPTZ NOT NULL,
  exit_ts  TIMESTAMPTZ NOT NULL,
  entry_price DOUBLE PRECISION NOT NULL,
  exit_price  DOUBLE PRECISION NOT NULL,
  tp_hit BOOLEAN, sl_hit BOOLEAN,
  bars_held INTEGER,
  pnl_pips DOUBLE PRECISION,
  pnl_ccy  DOUBLE PRECISION,
  commission_ccy DOUBLE PRECISION,
  slippage_pips  DOUBLE PRECISION,
  account_name   TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_replay_trades_run  ON replay_trades_shadow(run_id);
CREATE INDEX IF NOT EXISTS idx_replay_trades_key  ON replay_trades_shadow(instrument, entry_ts);

-- Run summary
CREATE TABLE IF NOT EXISTS replay_stats_shadow (
  run_id UUID PRIMARY KEY,
  instrument TEXT,
  horizon TEXT,
  trades INT,
  win_rate DOUBLE PRECISION,
  profit_factor DOUBLE PRECISION,
  expectancy_r DOUBLE PRECISION,
  sharpe_daily DOUBLE PRECISION,
  max_drawdown_ccy DOUBLE PRECISION,
  avg_rr DOUBLE PRECISION,
  start_ts TIMESTAMPTZ,
  end_ts   TIMESTAMPTZ,
  signals INT,   -- we’ll set to plan count for now
  plans   INT,
  oaat_blocks INT,
  embargo_blocks INT,
  deadband_bars INT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Equity curve
CREATE TABLE IF NOT EXISTS equity_curve_shadow (
  run_id UUID NOT NULL,
  ts     TIMESTAMPTZ NOT NULL,
  equity_ccy DOUBLE PRECISION NOT NULL,
  drawdown_ccy DOUBLE PRECISION,
  PRIMARY KEY (run_id, ts)
);


select * from replay_stats_shadow rss ;

select * from replay_trades_shadow rts ;

select * from plans_shadow ps ;

delete from replay_trades_shadow where run_id = '84987b44-43af-4a07-9b98-336a935f7e10';

ALTER TABLE replay_trades_shadow
  ADD COLUMN IF NOT EXISTS exit_reason TEXT;  -- 'tp' | 'sl' | 'horizon' | 'gtd_expire' | 'breach';
 
 
 SELECT
  COUNT(*) AS n,
  ROUND(AVG(rr)::numeric,2)      AS rr_mean,
  ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY rr)::numeric,2) AS rr_p50,
  ROUND(AVG(expected_r)::numeric,3) AS evR_mean
FROM plans_shadow
WHERE run_id = '37ca7889-e414-4712-810d-7b190b40f098';


SELECT exit_reason, COUNT(*) AS n,
       ROUND(AVG(pnl_ccy)::numeric,2) AS avg_pnl
FROM replay_trades_shadow
WHERE run_id = '37ca7889-e414-4712-810d-7b190b40f098'
GROUP BY exit_reason ORDER BY n DESC;


SELECT EXTRACT(HOUR FROM entry_ts) AS hh,
       COUNT(*) AS n,
       ROUND(AVG(pnl_ccy)::numeric,2) AS avg_pnl
FROM replay_trades_shadow
WHERE run_id = '37ca7889-e414-4712-810d-7b190b40f098'
GROUP BY 1 ORDER BY 1;

------------------------ GROK 4 ----------------------------------

CREATE TABLE IF NOT EXISTS enriched_candles_m1 (
    instrument TEXT,
    ts_utc TIMESTAMPTZ,
    bid_open NUMERIC(18,8),
    bid_high NUMERIC(18,8),
    bid_low NUMERIC(18,8),
    bid_close NUMERIC(18,8),
    ask_open NUMERIC(18,8),
    ask_high NUMERIC(18,8),
    ask_low NUMERIC(18,8),
    ask_close NUMERIC(18,8),
    spread_close NUMERIC,
    volume NUMERIC,
    tick_count INTEGER,
    source TEXT,
    data_source_type TEXT,
    data_quality_score NUMERIC,
    processing_latency_ms INTEGER,
    created_at_utc TIMESTAMPTZ,
    created_by TEXT,
    is_validated BOOLEAN,
    is_embargo BOOLEAN,
    hour INTEGER,  -- Derived
    session TEXT,
    atr NUMERIC,   -- Derived
    vol_flag TEXT
);
SELECT create_hypertable('enriched_candles_m1', 'ts_utc', if_not_exists => TRUE);  -- Partition on timestamp


CREATE TABLE IF NOT EXISTS featured_candles_m1 (
    instrument TEXT,
    ts_utc TIMESTAMPTZ,
    bid_open NUMERIC(18,8),
    bid_high NUMERIC(18,8),
    bid_low NUMERIC(18,8),
    bid_close NUMERIC(18,8),
    ask_open NUMERIC(18,8),
    ask_high NUMERIC(18,8),
    ask_low NUMERIC(18,8),
    ask_close NUMERIC(18,8),
    spread_close NUMERIC,
    volume NUMERIC,
    tick_count INTEGER,
    source TEXT,
    data_source_type TEXT,
    data_quality_score NUMERIC,
    processing_latency_ms INTEGER,
    created_at_utc TIMESTAMPTZ,
    created_by TEXT,
    is_validated BOOLEAN,
    is_embargo BOOLEAN,
    hour INTEGER,      -- From enrichment
    session TEXT,
    atr NUMERIC,
    vol_flag TEXT,
    fvg_bullish BOOLEAN,  -- SMC/ICT features
    fvg_bearish BOOLEAN,
    fvg_price NUMERIC,
    ob_high NUMERIC,
    ob_low NUMERIC,
    ema_fast NUMERIC,
    ema_slow NUMERIC,
    ema_bull_cross BOOLEAN,
    ema_bear_cross BOOLEAN,
    pattern_strength NUMERIC  -- Confidence precursor (0-1)
);
SELECT create_hypertable('featured_candles_m1', 'ts_utc', if_not_exists => TRUE);  -- Partition on timestamp


select * from enriched_candles_m1 where is_embargo = true
order by ts_utc desc;

 SELECT datetime_utc, event_name, currency, impact
            FROM macro_calendar_events
            WHERE impact = 'high'
            AND currency IN ('USD','JPY')
            AND datetime_utc BETWEEN '1999-12-31 00:00:00' AND '2025-09-30 23:59:59';
           
SELECT * FROM enriched_candles_m1 WHERE instrument='USDJPY' AND ts_utc BETWEEN '2025-09-01' AND '2025-09-30 23:59:59'

select * from macro_calendar_events mce order by  datetime_utc desc;


select * from featured_candles_m1 order by ts_utc desc;

SELECT * FROM featured_candles_m1 WHERE instrument='USDJPY' 
 and fvg_bearish = true
order by ts_utc ;

SELECT session, signal_strength
FROM featured_candles_m1
WHERE instrument='USDJPY'  and  session IN ('London', 'NY', 'London-NY Overlap') and signal_strength > 0;

TRUNCATE TABLE enriched_candles_m1;
TRUNCATE TABLE featured_candles_m1;

select * from market_data_m1 mdm order by "timestamp" desc ;

SELECT * FROM featured_candles_m1 WHERE instrument='USDJPY' AND ts_utc BETWEEN '2025-09-25 02:46:00' AND '2025-09-25 02:48:00' ORDER BY ts_utc;


SELECT table_name, column_name, data_type, numeric_precision, numeric_scale
FROM information_schema.columns 
WHERE table_name IN ('featured_candles_m1')
AND table_schema = 'public'
ORDER BY table_name, ordinal_position


SELECT session, COUNT(*) as signal_count
FROM featured_candles_m1
WHERE instrument='USDJPY' AND signal_strength > 0.5 AND session IN ('London', 'NY', 'London-NY Overlap')
GROUP BY session;


ALTER TABLE featured_candles_m1
ADD COLUMN IF NOT EXISTS fvg_top NUMERIC(18,8),
ADD COLUMN IF NOT EXISTS fvg_bottom NUMERIC(18,8),
ADD COLUMN IF NOT EXISTS ifvg_bullish BOOLEAN,
ADD COLUMN IF NOT EXISTS ifvg_bearish BOOLEAN,
ADD COLUMN IF NOT EXISTS mitigated BOOLEAN,
ADD COLUMN IF NOT EXISTS rsi NUMERIC,
ADD COLUMN IF NOT EXISTS macd NUMERIC,
ADD COLUMN IF NOT EXISTS macd_signal NUMERIC,
ADD COLUMN IF NOT EXISTS macd_bull_cross BOOLEAN,
ADD COLUMN IF NOT EXISTS macd_bear_cross BOOLEAN,
ADD COLUMN IF NOT EXISTS swing_high BOOLEAN,
ADD COLUMN IF NOT EXISTS swing_low BOOLEAN,
ADD COLUMN IF NOT EXISTS bos_bull BOOLEAN,
ADD COLUMN IF NOT EXISTS bos_bear BOOLEAN,
ADD COLUMN IF NOT EXISTS choch_bull BOOLEAN,
ADD COLUMN IF NOT EXISTS choch_bear BOOLEAN,
ADD COLUMN IF NOT EXISTS adx NUMERIC,
ADD COLUMN IF NOT EXISTS break_bull BOOLEAN,
ADD COLUMN IF NOT EXISTS break_bear BOOLEAN,
ADD COLUMN IF NOT EXISTS retest_bull BOOLEAN,
ADD COLUMN IF NOT EXISTS retest_bear BOOLEAN,
ADD COLUMN IF NOT EXISTS trend_bull BOOLEAN,
ADD COLUMN IF NOT EXISTS trend_bear BOOLEAN,
ADD COLUMN IF NOT EXISTS signal_strength NUMERIC,
ADD COLUMN IF NOT EXISTS signal_valid BOOLEAN,
ADD COLUMN IF NOT EXISTS sl_price NUMERIC(18,8),
ADD COLUMN IF NOT EXISTS tp_price NUMERIC(18,8);


SELECT table_name ,column_name, data_type, numeric_precision, numeric_scale
FROM information_schema.columns
WHERE table_name in ('market_data_m1','live_market_data_m1',
'macro_calendar_events', 'enriched_candles_m1','featured_candles_m1',
'backtest_results','backtest_trades');

ORDER BY column_name;

select * from v_candles_m1 vcm lmdm mce bt br ecm mdm 

SELECT ts_utc, fvg_bullish , fvg_bearish, ifvg_bullish, ifvg_bearish, retest_bull, retest_bear, trend_bull, trend_bear
FROM featured_candles_m1
WHERE instrument='USDJPY' and fvg_bullish = true
LIMIT 200;

SELECT ts_utc, bid_open, bid_high, bid_low, bid_close, atr
FROM enriched_candles_m1
WHERE instrument='USDJPY'
LIMIT 10;

SELECT session, COUNT(*) as signal_count
FROM featured_candles_m1
WHERE instrument='USDJPY' AND signal_strength > 0.5 AND session IN ('London', 'NY', 'London-NY Overlap')
GROUP BY session;


SELECT COUNT(*) as embargo_signals
FROM featured_candles_m1
WHERE instrument='USDJPY' AND signal_strength > 0.5 AND is_embargo = TRUE;

SELECT ts_utc, bid_close, fvg_bullish, fvg_bearish, ifvg_bullish, ifvg_bearish, signal_strength, session, sl_price, tp_price
FROM featured_candles_m1
WHERE instrument='USDJPY' AND signal_strength > 0.5 AND session IN ('London', 'NY', 'London-NY Overlap')
LIMIT 5;

ALTER TABLE featured_candles_m1
ADD COLUMN IF NOT EXISTS run_id UUID;

CREATE TABLE IF NOT EXISTS strategy_runs (
    run_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_name TEXT NOT NULL,
    strategy_json JSONB NOT NULL,
    run_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT,  -- Optional for multi-user
    notes TEXT     -- Optional for comments
);

SELECT * FROM pg_available_extensions WHERE name = 'uuid-ossp';

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
SELECT * FROM pg_extension WHERE extname = 'uuid-ossp';


CREATE TABLE IF NOT EXISTS strategy_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),  -- pgcrypto alternative
    strategy_name TEXT NOT NULL,
    strategy_json JSONB NOT NULL,
    run_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT,  -- Optional for multi-user
    notes TEXT     -- Optional for comments
);

select * from featured_candles_m1 fcm ;


ALTER TABLE featured_candles_m1
ADD COLUMN IF NOT EXISTS trade_type TEXT,
ADD COLUMN IF NOT EXISTS entry_price NUMERIC(18,8),
ADD COLUMN IF NOT EXISTS exit_price_tp NUMERIC(18,8),
ADD COLUMN IF NOT EXISTS exit_price_sl NUMERIC(18,8),
ADD COLUMN IF NOT EXISTS strategy_name TEXT,
ADD COLUMN IF NOT EXISTS run_id UUID;

ALTER TABLE featured_candles_m1
ADD CONSTRAINT fk_run_id FOREIGN KEY (run_id) REFERENCES strategy_runs(run_id);

SELECT * FROM strategy_runs ;

ALTER TABLE featured_candles_m1
ADD COLUMN IF NOT EXISTS trade_type TEXT,
ADD COLUMN IF NOT EXISTS entry_price NUMERIC(18,8),
ADD COLUMN IF NOT EXISTS exit_price_tp NUMERIC(18,8),
ADD COLUMN IF NOT EXISTS exit_price_sl NUMERIC(18,8),
ADD COLUMN IF NOT EXISTS strategy_name TEXT,
ADD COLUMN IF NOT EXISTS run_id UUID;

ALTER TABLE featured_candles_m1
ADD CONSTRAINT fk_run_id FOREIGN KEY (run_id) REFERENCES strategy_runs(run_id);


SELECT ts_utc, bid_close, fvg_bullish, fvg_bearish, ifvg_bullish, ifvg_bearish, signal_strength, session, trade_type, entry_price, sl_price, tp_price, exit_price_sl, exit_price_tp, strategy_name, run_id
FROM featured_candles_m1
WHERE instrument='USDJPY' AND signal_strength > 0.5 AND session IN ('London', 'NY', 'London-NY Overlap')
LIMIT 5;

select * from strategy_runs;

SELECT session, COUNT(*) as signal_count
FROM featured_candles_m1
WHERE instrument='USDJPY' AND signal_strength > 0.5 AND session IN ('London', 'NY', 'London-NY Overlap')
GROUP BY session;


SELECT ts_utc, bid_close, fvg_bullish, fvg_bearish, ifvg_bullish, ifvg_bearish, signal_strength, session, trade_type, entry_price, sl_price, tp_price, exit_price_sl, exit_price_tp, strategy_name, run_id
FROM featured_candles_m1
WHERE instrument='USDJPY' AND signal_strength > 0.5 AND session IN ('London', 'NY', 'London-NY Overlap')
order by ts_utc desc
LIMIT 5;


SELECT COUNT(*) as embargo_signals
FROM featured_candles_m1
WHERE instrument='USDJPY' AND signal_strength > 0.5 AND is_embargo = TRUE;


SELECT ts_utc, atr FROM enriched_candles_m1 LIMIT 10;


SELECT COUNT(*) as embargo_signals
FROM featured_candles_m1
WHERE instrument='USDJPY' AND signal_strength > 0.5 AND is_embargo = TRUE;


CREATE TABLE IF NOT EXISTS backtest_results (
    run_id UUID PRIMARY KEY,
    total_trades INTEGER NOT NULL,
    win_rate NUMERIC NOT NULL,
    profit_factor NUMERIC NOT NULL,
    rrr NUMERIC NOT NULL,
    max_drawdown NUMERIC NOT NULL,
    sharpe_ratio NUMERIC NOT NULL,
    total_pnl NUMERIC NOT NULL,
    avg_trade_duration INTERVAL,  -- Optional
    backtest_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES strategy_runs(run_id)
);

CREATE TABLE IF NOT EXISTS backtest_results (
    run_id UUID PRIMARY KEY,
    total_trades INTEGER NOT NULL,
    win_rate NUMERIC NOT NULL,
    profit_factor NUMERIC NOT NULL,
    rrr NUMERIC NOT NULL,
    max_drawdown NUMERIC NOT NULL,
    sharpe_ratio NUMERIC NOT NULL,
    total_pnl NUMERIC NOT NULL,
    avg_trade_duration INTERVAL,
    backtest_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES strategy_runs(run_id)
);


CREATE TABLE IF NOT EXISTS backtest_results (
    run_id UUID PRIMARY KEY,
    total_trades INTEGER NOT NULL,
    win_rate NUMERIC NOT NULL,
    profit_factor NUMERIC NOT NULL,
    rrr NUMERIC NOT NULL,
    max_drawdown NUMERIC NOT NULL,
    sharpe_ratio NUMERIC NOT NULL,
    total_pnl NUMERIC NOT NULL,
    avg_trade_duration INTERVAL,
    backtest_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES strategy_runs(run_id)
);


ALTER TABLE backtest_results
ADD COLUMN IF NOT EXISTS total_trades INTEGER NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS win_rate NUMERIC NOT NULL DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS profit_factor NUMERIC NOT NULL DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS rrr NUMERIC NOT NULL DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS max_drawdown NUMERIC NOT NULL DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS sharpe_ratio NUMERIC NOT NULL DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS total_pnl NUMERIC NOT NULL DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS avg_trade_duration INTERVAL,
ADD COLUMN IF NOT EXISTS backtest_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;


ALTER TABLE backtest_results ADD CONSTRAINT IF NOT EXISTS fk_run_id FOREIGN KEY (run_id) REFERENCES strategy_runs(run_id);

SELECT run_id, total_trades, win_rate, profit_factor, rrr, max_drawdown, sharpe_ratio, total_pnl
FROM backtest_results
WHERE run_id = 'ed4df474-3aad-45fd-af4a-4cf6fa8d7d0b';

select * from  backtest_results ;

CREATE TABLE IF NOT EXISTS backtest_results (
    run_id UUID PRIMARY KEY,
    total_trades INTEGER NOT NULL,
    win_rate NUMERIC NOT NULL,
    profit_factor NUMERIC NOT NULL,
    rrr NUMERIC NOT NULL,
    max_drawdown NUMERIC NOT NULL,
    sharpe_ratio NUMERIC NOT NULL,
    total_pnl NUMERIC NOT NULL,
    avg_trade_duration INTERVAL,
    backtest_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES strategy_runs(run_id)
);


SELECT ts_utc, bid_close, trade_type, entry_price, sl_price, tp_price, exit_price_sl, exit_price_tp
FROM featured_candles_m1
WHERE instrument='USDJPY' AND signal_strength > 0.5 AND session IN ('London', 'NY', 'London-NY Overlap')
order by ts_utc desc
LIMIT 10;


-- Add new columns to backtest_results
ALTER TABLE backtest_results
ADD COLUMN IF NOT EXISTS final_equity NUMERIC NOT NULL DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS max_day_loss NUMERIC NOT NULL DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS max_total_loss NUMERIC NOT NULL DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS avg_bars_held NUMERIC NOT NULL DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS avg_pnl_per_trade NUMERIC NOT NULL DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS equity_high NUMERIC NOT NULL DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS equity_low NUMERIC NOT NULL DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS total_wins INTEGER NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS total_losses INTEGER NOT NULL DEFAULT 0;

-- Create backtest_trades table
CREATE TABLE IF NOT EXISTS backtest_trades (
    trade_id SERIAL PRIMARY KEY,
    run_id UUID NOT NULL,
    entry_time TIMESTAMP WITH TIME ZONE,
    exit_time TIMESTAMP WITH TIME ZONE,
    trade_type TEXT NOT NULL,
    entry_price NUMERIC(18,8) NOT NULL,
    exit_price NUMERIC(18,8) NOT NULL,
    pnl_pips NUMERIC NOT NULL,
    pnl_dollars NUMERIC NOT NULL,
    bars_held INTEGER NOT NULL,
    FOREIGN KEY (run_id) REFERENCES strategy_runs(run_id)
);

ALTER TABLE backtest_results
ADD COLUMN IF NOT EXISTS final_equity NUMERIC NOT NULL DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS max_day_loss NUMERIC NOT NULL DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS max_total_loss NUMERIC NOT NULL DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS avg_bars_held NUMERIC NOT NULL DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS avg_pnl_per_trade NUMERIC NOT NULL DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS equity_high NUMERIC NOT NULL DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS equity_low NUMERIC NOT NULL DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS total_wins INTEGER NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS total_losses INTEGER NOT NULL DEFAULT 0;
truncate table backtest_results ;

select * from backtest_results br;

select * from backtest_trades br;

ALTER TABLE backtest_results
ADD COLUMN IF NOT EXISTS skipped_trades INTEGER NOT NULL DEFAULT 0;

-- Update backtest_trades to include trade_type
ALTER TABLE backtest_trades
ADD COLUMN IF NOT EXISTS trade_type TEXT NOT NULL DEFAULT 'unknown';

-- Update backtest_trades to include pnl_pips
ALTER TABLE backtest_trades
ADD COLUMN IF NOT EXISTS pnl_pips NUMERIC(18, 8) NOT NULL DEFAULT 0.0;

DROP TABLE IF EXISTS backtest_trades;
CREATE TABLE backtest_trades (
    trade_id SERIAL PRIMARY KEY,
    run_id UUID NOT NULL,
    entry_time TIMESTAMP WITH TIME ZONE,
    exit_time TIMESTAMP WITH TIME ZONE,
    trade_type TEXT NOT NULL DEFAULT 'unknown',
    entry_price NUMERIC(18, 8) NOT NULL,
    exit_price NUMERIC(18, 8) NOT NULL,
    pnl_pips NUMERIC(18, 8) NOT NULL DEFAULT 0.0,
    pnl_dollars NUMERIC NOT NULL,
    bars_held INTEGER NOT NULL,
    lot_size NUMERIC(10, 2) NOT NULL DEFAULT 0.01,
    FOREIGN KEY (run_id) REFERENCES strategy_runs(run_id)
);

ALTER TABLE backtest_trades
ADD COLUMN IF NOT EXISTS pnl_pips NUMERIC(18, 8) NOT NULL DEFAULT 0.0;


ALTER TABLE backtest_trades
ADD COLUMN IF NOT EXISTS pnl_pips NUMERIC(18, 8) NOT NULL DEFAULT 0.0;
truncate table backtest_trades; 


DROP TABLE IF EXISTS backtest_trades;
CREATE TABLE backtest_trades (
    trade_id SERIAL PRIMARY KEY,
    run_id UUID NOT NULL,
    entry_time TIMESTAMP WITH TIME ZONE,
    exit_time TIMESTAMP WITH TIME ZONE,
    trade_type TEXT NOT NULL DEFAULT 'unknown',
    entry_price NUMERIC(18, 8) NOT NULL,
    exit_price NUMERIC(18, 8) NOT NULL,
    pnl_pips NUMERIC(18, 8) NOT NULL DEFAULT 0.0,
    pnl_dollars NUMERIC NOT NULL,
    bars_held INTEGER NOT NULL,
    lot_size NUMERIC(10, 2) NOT NULL DEFAULT 0.01,
    FOREIGN KEY (run_id) REFERENCES strategy_runs(run_id)
);

ALTER TABLE backtest_results
ADD COLUMN IF NOT EXISTS avg_trade_duration NUMERIC(18, 8) NOT NULL DEFAULT 0;


-- Drop the existing backtest_results table if it exists
DROP TABLE IF EXISTS backtest_results;

-- Create the backtest_results table with all required columns
CREATE TABLE backtest_results (
    run_id UUID PRIMARY KEY,
    total_trades INTEGER NOT NULL DEFAULT 0,
    win_rate NUMERIC NOT NULL DEFAULT 0.0,
    profit_factor NUMERIC NOT NULL DEFAULT 0.0,
    rrr NUMERIC NOT NULL DEFAULT 0.0,
    max_drawdown NUMERIC NOT NULL DEFAULT 0.0,
    sharpe_ratio NUMERIC NOT NULL DEFAULT 0.0,
    total_pnl NUMERIC NOT NULL DEFAULT 0.0,
    avg_trade_duration NUMERIC NOT NULL DEFAULT 0.0,
    final_equity NUMERIC NOT NULL DEFAULT 0.0,
    max_day_loss NUMERIC NOT NULL DEFAULT 0.0,
    max_total_loss NUMERIC NOT NULL DEFAULT 0.0,
    avg_bars_held NUMERIC NOT NULL DEFAULT 0.0,
    avg_pnl_per_trade NUMERIC NOT NULL DEFAULT 0.0,
    equity_high NUMERIC NOT NULL DEFAULT 0.0,
    equity_low NUMERIC NOT NULL DEFAULT 0.0,
    total_wins INTEGER NOT NULL DEFAULT 0,
    total_losses INTEGER NOT NULL DEFAULT 0,
    skipped_trades INTEGER NOT NULL DEFAULT 0,
    backtest_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);


SELECT * FROM backtest_results
WHERE run_id = 'ed4df474-3aad-45fd-af4a-4cf6fa8d7d0b';

select * from backtest_trades bt order by entry_time ;

-- Add commission_cost and equity_after_trade to backtest_trades
ALTER TABLE backtest_trades
ADD COLUMN IF NOT EXISTS signal_strength NUMERIC NOT NULL DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS equity_after_trade NUMERIC NOT NULL DEFAULT 0.0;

SELECT entry_time, pnl_dollars, commission_cost, equity_after_trade
FROM backtest_trades
ORDER BY entry_time;

truncate table backtest_trades;
truncate table backtest_results;
truncate table enriched_candles_m1 ;
truncate table featured_candles_m1 ;

select * from featured_candles_m1 fcm order by ts_utc desc;


select * from enriched_candles_m1 ecm order by ts_utc desc;

select count(*) from enriched_candles_m1;

select * from v_candles_m1 vcm ;

select * from backtest_runs br ;

SELECT *  FROM market_data_m1 order by "timestamp" desc;
       
select * from v_candles_m1 vcm limit 10;

SELECT AVG(atr) FROM featured_candles_m1;

-- Alter table to add missing columns based on feature_engineer.py output
ALTER TABLE featured_candles_m1
    ADD COLUMN IF NOT EXISTS rsi numeric,
    ADD COLUMN IF NOT EXISTS is_oversold boolean,
    ADD COLUMN IF NOT EXISTS is_overbought boolean,
    ADD COLUMN IF NOT EXISTS macd numeric,
    ADD COLUMN IF NOT EXISTS macd_signal numeric,
    ADD COLUMN IF NOT EXISTS macd_bull_cross boolean,
    ADD COLUMN IF NOT EXISTS macd_bear_cross boolean,
    ADD COLUMN IF NOT EXISTS ema_fast numeric,
    ADD COLUMN IF NOT EXISTS ema_slow numeric,
    ADD COLUMN IF NOT EXISTS ema_bull_cross boolean,
    ADD COLUMN IF NOT EXISTS ema_bear_cross boolean,
    ADD COLUMN IF NOT EXISTS adx numeric,
    ADD COLUMN IF NOT EXISTS trend_bull boolean,
    ADD COLUMN IF NOT EXISTS trend_bear boolean,
    ADD COLUMN IF NOT EXISTS fvg_bullish boolean,
    ADD COLUMN IF NOT EXISTS fvg_bearish boolean,
    ADD COLUMN IF NOT EXISTS ifvg_bullish boolean,
    ADD COLUMN IF NOT EXISTS ifvg_bearish boolean,
    ADD COLUMN IF NOT EXISTS order_block_bull boolean,
    ADD COLUMN IF NOT EXISTS order_block_bear boolean,
    ADD COLUMN IF NOT EXISTS breaker_bull boolean,
    ADD COLUMN IF NOT EXISTS breaker_bear boolean,
    ADD COLUMN IF NOT EXISTS mitigation_bull boolean,
    ADD COLUMN IF NOT EXISTS mitigation_bear boolean,
    ADD COLUMN IF NOT EXISTS imbalance_bull boolean,
    ADD COLUMN IF NOT EXISTS imbalance_bear boolean,
    ADD COLUMN IF NOT EXISTS bos_bull boolean,
    ADD COLUMN IF NOT EXISTS bos_bear boolean,
    ADD COLUMN IF NOT EXISTS choch_bull boolean,
    ADD COLUMN IF NOT EXISTS choch_bear boolean,
    ADD COLUMN IF NOT EXISTS liquidity_grab_bull boolean,
    ADD COLUMN IF NOT EXISTS liquidity_grab_bear boolean,
    ADD COLUMN IF NOT EXISTS pullback_bull boolean,
    ADD COLUMN IF NOT EXISTS pullback_bear boolean,
    ADD COLUMN IF NOT EXISTS reversal_bull boolean,
    ADD COLUMN IF NOT EXISTS reversal_bear boolean,
    ADD COLUMN IF NOT EXISTS inducement_bull boolean,
    ADD COLUMN IF NOT EXISTS inducement_bear boolean,
    ADD COLUMN IF NOT EXISTS swing_high boolean,
    ADD COLUMN IF NOT EXISTS swing_low boolean,
    ADD COLUMN IF NOT EXISTS sl_price numeric(18,8),
    ADD COLUMN IF NOT EXISTS tp_price numeric(18,8),
    ADD COLUMN IF NOT EXISTS trade_type text,
    ADD COLUMN IF NOT EXISTS entry_price numeric(18,8),
    ADD COLUMN IF NOT EXISTS exit_price_tp numeric(18,8),
    ADD COLUMN IF NOT EXISTS exit_price_sl numeric(18,8),
    ADD COLUMN IF NOT EXISTS signal_strength numeric,
    ADD COLUMN IF NOT EXISTS signal_valid boolean;

-- Optional: Add indexes for performance (if not already present)
CREATE INDEX IF NOT EXISTS idx_featured_candles_m1_ts_utc ON featured_candles_m1 (ts_utc);
CREATE INDEX IF NOT EXISTS idx_featured_candles_m1_instrument ON featured_candles_m1 (instrument);


ALTER TABLE featured_candles_m1
    DROP COLUMN IF EXISTS swing_high,
    DROP COLUMN IF EXISTS swing_low;
    
ALTER TABLE featured_candles_m1
    ADD COLUMN swing_high numeric(18,8),
    ADD COLUMN swing_low numeric(18,8);
    
   
   SELECT ts_utc, bid_close, trade_type, entry_price, sl_price, tp_price, exit_price_sl, exit_price_tp, session, run_id, signal_strength
        FROM featured_candles_m1
        WHERE instrument='USDJPY' AND trade_type= 'long' AND session IN ('London', 'NY', 'London-NY Overlap')
        
        
-- Enable UUID generation if not already present
CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE IF EXISTS public.featured_candles_m1
  ADD COLUMN IF NOT EXISTS signal_id UUID DEFAULT gen_random_uuid(),
  ADD COLUMN IF NOT EXISTS run_id UUID,
  ADD COLUMN IF NOT EXISTS feature_set_version TEXT,
  ADD COLUMN IF NOT EXISTS timeframe TEXT,
  ADD COLUMN IF NOT EXISTS strategy TEXT,
  ADD COLUMN IF NOT EXISTS direction TEXT,                 -- LONG / SHORT
  ADD COLUMN IF NOT EXISTS session_broker_tz TEXT,         -- london/ny/overlap/tokyo/off
  ADD COLUMN IF NOT EXISTS is_embargo BOOLEAN,
  ADD COLUMN IF NOT EXISTS minutes_to_event INT,
  ADD COLUMN IF NOT EXISTS event_impact TEXT,              -- low/medium/high (if known)
  -- Core market/indicator context (kept for lineage)
  ADD COLUMN IF NOT EXISTS atr DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS adx DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS ema_fast DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS ema_slow DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS spread_close DOUBLE PRECISION,
  -- FVG geometry
  ADD COLUMN IF NOT EXISTS fvg_type TEXT,                  -- bullish / bearish
  ADD COLUMN IF NOT EXISTS fvg_top DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS fvg_bottom DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS fvg_mid DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS fvg_state TEXT,                 -- open / mitigated (at creation time it's 'open')
  -- Signal proposal (not realized PnL)
  ADD COLUMN IF NOT EXISTS entry_basis TEXT,               -- mid|top|bottom (or rule)
  ADD COLUMN IF NOT EXISTS sl_basis TEXT,
  ADD COLUMN IF NOT EXISTS tp_basis TEXT,
  ADD COLUMN IF NOT EXISTS rr_target DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS entry_price DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS sl_price DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS tp_price DOUBLE PRECISION,
  -- Scoring & explanations
  ADD COLUMN IF NOT EXISTS signal_score DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS pattern_primary TEXT,           -- e.g., 'FVG-PB'
  ADD COLUMN IF NOT EXISTS pattern_secondary JSONB,        -- e.g., ["EMA align","ADX regime"]
  ADD COLUMN IF NOT EXISTS reason_codes JSONB;             -- detailed flags that fired

-- Practical uniqueness guard for a run's signal set
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM   pg_indexes
    WHERE  schemaname = 'public'
    AND    indexname  = 'ux_featured_m1_inst_ts_strategy_run'
  ) THEN
    CREATE UNIQUE INDEX ux_featured_m1_inst_ts_strategy_run
      ON public.featured_candles_m1 (instrument, ts_utc, strategy, run_id);
  END IF;
END$$;


SELECT table_name, column_name, data_type, numeric_precision, numeric_scale
FROM information_schema.columns 
WHERE table_name IN ('enriched_candles_m1')
AND table_schema = 'public'
ORDER BY table_name, ordinal_position
