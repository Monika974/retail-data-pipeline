-- 00_init.sql : schemas, audit tables and safe-parsing helper functions (idempotent)

CREATE SCHEMA IF NOT EXISTS raw;       -- landing zone: source data exactly as received (TEXT)
CREATE SCHEMA IF NOT EXISTS staging;   -- cleaned, typed, de-duplicated, validated
CREATE SCHEMA IF NOT EXISTS marts;     -- analytics-ready dimensions, facts and aggregates
CREATE SCHEMA IF NOT EXISTS ops;       -- pipeline metadata: runs, steps, quarantine, DQ results

CREATE TABLE IF NOT EXISTS ops.pipeline_runs (
    run_id       TEXT PRIMARY KEY,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ,
    status       TEXT NOT NULL DEFAULT 'running'      -- running | success | failed
);

CREATE TABLE IF NOT EXISTS ops.pipeline_steps (
    id            BIGSERIAL PRIMARY KEY,
    run_id        TEXT NOT NULL REFERENCES ops.pipeline_runs (run_id),
    step          TEXT NOT NULL,
    status        TEXT NOT NULL,                      -- success | failed
    rows_affected BIGINT,
    duration_s    NUMERIC(10, 3),
    message       TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.quarantine (
    id             BIGSERIAL PRIMARY KEY,
    run_id         TEXT NOT NULL,
    source_table   TEXT NOT NULL,
    record_key     TEXT,
    reason         TEXT NOT NULL,
    payload        JSONB NOT NULL,
    quarantined_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_quarantine_run ON ops.quarantine (run_id, source_table);

CREATE TABLE IF NOT EXISTS ops.dq_results (
    id          BIGSERIAL PRIMARY KEY,
    run_id      TEXT NOT NULL,
    check_name  TEXT NOT NULL,
    table_name  TEXT NOT NULL,
    severity    TEXT NOT NULL,                        -- error | warn
    violations  BIGINT NOT NULL,
    passed      BOOLEAN NOT NULL,
    checked_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Safe parsers: return NULL instead of raising, so one bad value never kills a whole load.
CREATE OR REPLACE FUNCTION ops.parse_date(t TEXT) RETURNS DATE AS $$
BEGIN
    IF t IS NULL THEN RETURN NULL; END IF;
    IF btrim(t) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN
        RETURN btrim(t)::date;
    ELSIF btrim(t) ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}$' THEN
        RETURN to_date(btrim(t), 'DD/MM/YYYY');
    END IF;
    RETURN NULL;
EXCEPTION WHEN others THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION ops.parse_int(t TEXT) RETURNS INTEGER AS $$
BEGIN
    IF t IS NULL OR btrim(t) !~ '^-?[0-9]+$' THEN RETURN NULL; END IF;
    RETURN btrim(t)::integer;
EXCEPTION WHEN others THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION ops.parse_num(t TEXT) RETURNS NUMERIC AS $$
BEGIN
    IF t IS NULL OR btrim(t) !~ '^-?[0-9]+(\.[0-9]+)?$' THEN RETURN NULL; END IF;
    RETURN btrim(t)::numeric;
EXCEPTION WHEN others THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql IMMUTABLE;
