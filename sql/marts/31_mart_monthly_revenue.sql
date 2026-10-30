-- Monthly revenue by country and category (grain for the BI dashboard).
DROP TABLE IF EXISTS marts.mart_monthly_revenue CASCADE;

CREATE TABLE marts.mart_monthly_revenue AS
SELECT
    date_trunc('month', f.order_date)::date AS month,
    c.country,
    f.category,
    COUNT(DISTINCT f.order_id)              AS orders,
    SUM(f.quantity)                         AS units,
    SUM(f.net_amount)                       AS net_revenue
FROM marts.fct_order_items f
JOIN staging.stg_customers c ON c.customer_id = f.customer_id
WHERE f.order_status = 'completed'
GROUP BY 1, 2, 3;
