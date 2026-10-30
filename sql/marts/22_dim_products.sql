DROP TABLE IF EXISTS marts.dim_products CASCADE;

CREATE TABLE marts.dim_products AS
SELECT product_id, product_name, category, unit_price AS list_price
FROM staging.stg_products;

ALTER TABLE marts.dim_products ADD PRIMARY KEY (product_id);
