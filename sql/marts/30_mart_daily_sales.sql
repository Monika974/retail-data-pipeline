-- Daily sales with a true calendar 7-day rolling revenue (RANGE window, not ROWS).
DROP TABLE IF EXISTS marts.mart_daily_sales CASCADE;

CREATE TABLE marts.mart_daily_sales AS
WITH daily AS (
    SELECT order_date,
           COUNT(DISTINCT order_id) AS orders,
           SUM(quantity)            AS units,
           SUM(net_amount)          AS net_revenue
    FROM marts.fct_order_items
    WHERE order_status = 'completed'
    GROUP BY order_date
)
SELECT
    order_date,
    orders,
    units,
    net_revenue,
    ROUND(net_revenue / orders, 2) AS avg_order_value,
    ROUND(SUM(net_revenue) OVER (
        ORDER BY order_date
        RANGE BETWEEN INTERVAL '6 days' PRECEDING AND CURRENT ROW
    ), 2)                          AS rolling_7d_revenue
FROM daily;

ALTER TABLE marts.mart_daily_sales ADD PRIMARY KEY (order_date);
