-- 01_raw_tables.sql : landing tables. Every source column is TEXT so a load never fails on
-- bad data; typing and validation happen in staging, where rejects are quarantined, not lost.

CREATE TABLE IF NOT EXISTS raw.customers (
    customer_id TEXT, full_name TEXT, email TEXT, country TEXT, signup_date TEXT,
    _row_num BIGINT GENERATED ALWAYS AS IDENTITY,
    _batch_id TEXT,
    _loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.products (
    product_id TEXT, product_name TEXT, category TEXT, unit_price TEXT,
    _row_num BIGINT GENERATED ALWAYS AS IDENTITY,
    _batch_id TEXT,
    _loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.orders (
    order_id TEXT, customer_id TEXT, order_date TEXT, status TEXT,
    _row_num BIGINT GENERATED ALWAYS AS IDENTITY,
    _batch_id TEXT,
    _loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.order_items (
    order_item_id TEXT, order_id TEXT, product_id TEXT, quantity TEXT, unit_price TEXT,
    discount_pct TEXT,
    _row_num BIGINT GENERATED ALWAYS AS IDENTITY,
    _batch_id TEXT,
    _loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
