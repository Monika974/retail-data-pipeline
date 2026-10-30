DROP TABLE IF EXISTS staging.stg_orders CASCADE;

CREATE TEMP TABLE _ord ON COMMIT DROP AS
SELECT
    o._row_num,
    NULLIF(btrim(o.order_id), '')     AS order_id,
    NULLIF(btrim(o.customer_id), '')  AS customer_id,
    ops.parse_date(o.order_date)      AS order_date,
    CASE lower(btrim(o.status))
        WHEN 'completed' THEN 'completed'
        WHEN 'cancelled' THEN 'cancelled'
        WHEN 'canceled'  THEN 'cancelled'
        WHEN 'returned'  THEN 'returned'
        WHEN 'pending'   THEN 'pending'
    END                               AS status,
    o._batch_id,
    o._loaded_at,
    row_number() OVER (PARTITION BY NULLIF(btrim(o.order_id), '')
                       ORDER BY o._row_num) AS rn,
    to_jsonb(o)                       AS payload
FROM raw.orders o;

CREATE TEMP TABLE _ord_flagged ON COMMIT DROP AS
SELECT o.*,
       CASE
           WHEN o.order_id IS NULL THEN 'missing_key'
           WHEN o.rn > 1 THEN 'duplicate_key'
           WHEN o.order_date IS NULL THEN 'invalid_date'
           WHEN o.status IS NULL THEN 'invalid_status'
           WHEN NOT EXISTS (SELECT 1 FROM staging.stg_customers c
                            WHERE c.customer_id = o.customer_id) THEN 'orphan_customer'
       END AS reject_reason
FROM _ord o;

INSERT INTO ops.quarantine (run_id, source_table, record_key, reason, payload)
SELECT %(run_id)s, 'orders', COALESCE(order_id, 'row:' || _row_num), reject_reason, payload
FROM _ord_flagged
WHERE reject_reason IS NOT NULL;

CREATE TABLE staging.stg_orders AS
SELECT order_id, customer_id, order_date, status, _batch_id, _loaded_at
FROM _ord_flagged
WHERE reject_reason IS NULL;

ALTER TABLE staging.stg_orders ADD PRIMARY KEY (order_id);
ALTER TABLE staging.stg_orders
    ADD FOREIGN KEY (customer_id) REFERENCES staging.stg_customers (customer_id);
CREATE INDEX ix_stg_orders_date ON staging.stg_orders (order_date);
