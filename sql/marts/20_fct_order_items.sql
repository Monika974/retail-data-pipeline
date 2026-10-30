-- Fact table: one row per order line, enriched with order + product attributes.
DROP TABLE IF EXISTS marts.fct_order_items CASCADE;

CREATE TABLE marts.fct_order_items AS
SELECT
    i.order_item_id,
    i.order_id,
    o.order_date,
    o.customer_id,
    i.product_id,
    p.category,
    o.status                                                        AS order_status,
    i.quantity,
    i.unit_price,
    i.discount_pct,
    ROUND(i.quantity * i.unit_price, 2)                             AS gross_amount,
    ROUND(i.quantity * i.unit_price * (1 - i.discount_pct / 100.0), 2) AS net_amount
FROM staging.stg_order_items i
JOIN staging.stg_orders   o ON o.order_id   = i.order_id
JOIN staging.stg_products p ON p.product_id = i.product_id;

ALTER TABLE marts.fct_order_items ADD PRIMARY KEY (order_item_id);
CREATE INDEX ix_fct_date     ON marts.fct_order_items (order_date);
CREATE INDEX ix_fct_customer ON marts.fct_order_items (customer_id);
CREATE INDEX ix_fct_product  ON marts.fct_order_items (product_id);
