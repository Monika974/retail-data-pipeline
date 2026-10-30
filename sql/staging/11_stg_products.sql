DROP TABLE IF EXISTS staging.stg_products CASCADE;

CREATE TEMP TABLE _prod ON COMMIT DROP AS
SELECT
    p._row_num,
    NULLIF(btrim(p.product_id), '')    AS product_id,
    btrim(p.product_name)              AS product_name,
    initcap(btrim(p.category))         AS category,
    ops.parse_num(p.unit_price)        AS unit_price,
    p._batch_id,
    p._loaded_at,
    row_number() OVER (PARTITION BY NULLIF(btrim(p.product_id), '')
                       ORDER BY p._row_num) AS rn,
    to_jsonb(p)                        AS payload
FROM raw.products p;

INSERT INTO ops.quarantine (run_id, source_table, record_key, reason, payload)
SELECT %(run_id)s, 'products', COALESCE(product_id, 'row:' || _row_num),
       CASE WHEN product_id IS NULL THEN 'missing_key'
            WHEN rn > 1 THEN 'duplicate_key'
            ELSE 'invalid_price' END,
       payload
FROM _prod
WHERE product_id IS NULL OR rn > 1 OR unit_price IS NULL OR unit_price <= 0;

CREATE TABLE staging.stg_products AS
SELECT product_id, product_name, category, unit_price, _batch_id, _loaded_at
FROM _prod
WHERE product_id IS NOT NULL AND rn = 1 AND unit_price IS NOT NULL AND unit_price > 0;

ALTER TABLE staging.stg_products ADD PRIMARY KEY (product_id);
