DROP TABLE IF EXISTS marts.mart_product_performance CASCADE;

CREATE TABLE marts.mart_product_performance AS
WITH agg AS (
    SELECT
        p.product_id, p.product_name, p.category,
        COALESCE(SUM(f.quantity)   FILTER (WHERE f.order_status = 'completed'), 0) AS units_sold,
        COALESCE(SUM(f.net_amount) FILTER (WHERE f.order_status = 'completed'), 0) AS net_revenue,
        COUNT(*) FILTER (WHERE f.order_status = 'returned')                        AS returned_lines,
        COUNT(*) FILTER (WHERE f.order_status IN ('completed', 'returned'))        AS fulfilled_lines
    FROM marts.dim_products p
    LEFT JOIN marts.fct_order_items f ON f.product_id = p.product_id
    GROUP BY p.product_id, p.product_name, p.category
)
SELECT
    agg.*,
    ROUND(returned_lines::numeric / NULLIF(fulfilled_lines, 0), 4)        AS return_rate,
    RANK() OVER (PARTITION BY category ORDER BY net_revenue DESC)         AS revenue_rank_in_category
FROM agg;

ALTER TABLE marts.mart_product_performance ADD PRIMARY KEY (product_id);
