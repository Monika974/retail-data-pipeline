DROP TABLE IF EXISTS staging.stg_order_items CASCADE;

CREATE TEMP TABLE _item ON COMMIT DROP AS
SELECT
    i._row_num,
    NULLIF(btrim(i.order_item_id), '')            AS order_item_id,
    NULLIF(btrim(i.order_id), '')                 AS order_id,
    NULLIF(btrim(i.product_id), '')               AS product_id,
    ops.parse_int(i.quantity)                     AS quantity,
    ops.parse_num(i.unit_price)                   AS unit_price,
    COALESCE(ops.parse_num(i.discount_pct), 0)    AS discount_pct,
    i._batch_id,
    i._loaded_at,
    row_number() OVER (PARTITION BY NULLIF(btrim(i.order_item_id), '')
                       ORDER BY i._row_num)       AS rn,
    to_jsonb(i)                                   AS payload
FROM raw.order_items i;

CREATE TEMP TABLE _item_flagged ON COMMIT DROP AS
SELECT t.*,
       CASE
           WHEN t.order_item_id IS NULL THEN 'missing_key'
           WHEN t.rn > 1 THEN 'duplicate_key'
           WHEN t.quantity IS NULL OR t.quantity <= 0 THEN 'invalid_quantity'
           WHEN t.unit_price IS NULL OR t.unit_price <= 0 THEN 'invalid_price'
           WHEN t.discount_pct < 0 OR t.discount_pct > 100 THEN 'invalid_discount'
           WHEN NOT EXISTS (SELECT 1 FROM staging.stg_orders o
                            WHERE o.order_id = t.order_id) THEN 'orphan_order'
           WHEN NOT EXISTS (SELECT 1 FROM staging.stg_products p
                            WHERE p.product_id = t.product_id) THEN 'orphan_product'
       END AS reject_reason
FROM _item t;

INSERT INTO ops.quarantine (run_id, source_table, record_key, reason, payload)
SELECT %(run_id)s, 'order_items', COALESCE(order_item_id, 'row:' || _row_num),
       reject_reason, payload
FROM _item_flagged
WHERE reject_reason IS NOT NULL;

CREATE TABLE staging.stg_order_items AS
SELECT order_item_id, order_id, product_id, quantity, unit_price, discount_pct,
       _batch_id, _loaded_at
FROM _item_flagged
WHERE reject_reason IS NULL;

ALTER TABLE staging.stg_order_items ADD PRIMARY KEY (order_item_id);
ALTER TABLE staging.stg_order_items
    ADD FOREIGN KEY (order_id) REFERENCES staging.stg_orders (order_id);
ALTER TABLE staging.stg_order_items
    ADD FOREIGN KEY (product_id) REFERENCES staging.stg_products (product_id);
CREATE INDEX ix_stg_items_order ON staging.stg_order_items (order_id);
