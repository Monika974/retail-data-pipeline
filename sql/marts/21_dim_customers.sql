-- Customer dimension with lifetime metrics (completed orders only count as revenue).
DROP TABLE IF EXISTS marts.dim_customers CASCADE;

CREATE TABLE marts.dim_customers AS
SELECT
    c.customer_id,
    c.full_name,
    c.email,
    c.country,
    c.signup_date,
    MIN(f.order_date)                       AS first_order_date,
    MAX(f.order_date)                       AS last_order_date,
    COUNT(DISTINCT f.order_id)              AS lifetime_orders,
    COALESCE(SUM(f.net_amount), 0)          AS lifetime_revenue
FROM staging.stg_customers c
LEFT JOIN marts.fct_order_items f
       ON f.customer_id = c.customer_id AND f.order_status = 'completed'
GROUP BY c.customer_id, c.full_name, c.email, c.country, c.signup_date;

ALTER TABLE marts.dim_customers ADD PRIMARY KEY (customer_id);
