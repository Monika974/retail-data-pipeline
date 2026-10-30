# Data dictionary

## Source files (contract enforced by `extract.py`)

| File | Columns |
|---|---|
| customers.csv | customer_id, full_name, email, country, signup_date |
| products.csv | product_id, product_name, category, unit_price |
| orders.csv | order_id, customer_id, order_date, status |
| order_items.csv | order_item_id, order_id, product_id, quantity, unit_price, discount_pct |

## Cleaning rules (staging)

| Table | Rule | Rejected rows -> `ops.quarantine.reason` |
|---|---|---|
| stg_customers | trim; `initcap` names; lower-case email (empty -> NULL); standardise country (`IN`/`india` -> India, `US`/`USA` -> United States, `UK`/`GB` -> United Kingdom ...); parse mixed date formats; keep first row per `customer_id` | `missing_key`, `duplicate_key` |
| stg_products | trim; `initcap` category; numeric price | `missing_key`, `duplicate_key`, `invalid_price` |
| stg_orders | parse mixed date formats; normalise status (`canceled` -> `cancelled`, any casing) | `missing_key`, `duplicate_key`, `invalid_date`, `invalid_status`, `orphan_customer` |
| stg_order_items | integer quantity, numeric prices, missing discount -> 0 | `missing_key`, `duplicate_key`, `invalid_quantity`, `invalid_price`, `invalid_discount`, `orphan_order`, `orphan_product` |

Each rejected row is stored once, with the first matching reason (in the order listed) and the
original row as JSON in `payload`.

## Marts

| Table | Grain | Key columns |
|---|---|---|
| fct_order_items | one row per order line | gross_amount = qty x price; net_amount = gross x (1 - discount/100) |
| dim_customers | one row per customer | first/last order date, lifetime_orders, lifetime_revenue (completed only) |
| dim_products | one row per product | list_price |
| mart_daily_sales | one row per day | orders, units, net_revenue, avg_order_value, rolling_7d_revenue |
| mart_monthly_revenue | month x country x category | orders, units, net_revenue |
| mart_customer_rfm | one row per purchasing customer | recency_days, frequency, monetary, r/f/m scores (1-5), segment |
| mart_product_performance | one row per product | units_sold, net_revenue, return_rate, revenue_rank_in_category |

RFM segments: Champions, Loyal high-value, Recent customers, At risk, Lapsed, Regular.
