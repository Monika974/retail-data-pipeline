-- RFM segmentation: recency / frequency / monetary scored 1-5 with NTILE, then labelled.
DROP TABLE IF EXISTS marts.mart_customer_rfm CASCADE;

CREATE TABLE marts.mart_customer_rfm AS
WITH base AS (
    SELECT customer_id,
           MAX(order_date)            AS last_order_date,
           COUNT(DISTINCT order_id)   AS frequency,
           SUM(net_amount)            AS monetary
    FROM marts.fct_order_items
    WHERE order_status = 'completed'
    GROUP BY customer_id
),
ref AS (SELECT MAX(last_order_date) AS as_of_date FROM base),
scored AS (
    SELECT b.*,
           (r.as_of_date - b.last_order_date)                           AS recency_days,
           NTILE(5) OVER (ORDER BY (r.as_of_date - b.last_order_date) DESC) AS r_score,
           NTILE(5) OVER (ORDER BY b.frequency)                         AS f_score,
           NTILE(5) OVER (ORDER BY b.monetary)                          AS m_score
    FROM base b CROSS JOIN ref r
)
SELECT
    s.customer_id,
    c.country,
    s.last_order_date,
    s.recency_days,
    s.frequency,
    s.monetary,
    s.r_score, s.f_score, s.m_score,
    CASE
        WHEN s.r_score >= 4 AND s.f_score >= 4                    THEN 'Champions'
        WHEN s.f_score >= 4 AND s.m_score >= 4                    THEN 'Loyal high-value'
        WHEN s.r_score >= 4                                       THEN 'Recent customers'
        WHEN s.r_score <= 2 AND (s.f_score >= 3 OR s.m_score >= 3) THEN 'At risk'
        WHEN s.r_score <= 2                                       THEN 'Lapsed'
        ELSE 'Regular'
    END AS segment
FROM scored s
JOIN staging.stg_customers c ON c.customer_id = s.customer_id;

ALTER TABLE marts.mart_customer_rfm ADD PRIMARY KEY (customer_id);
