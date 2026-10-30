-- Clean + de-duplicate customers. Rejected rows go to ops.quarantine with a reason.
DROP TABLE IF EXISTS staging.stg_customers CASCADE;

CREATE TEMP TABLE _cust ON COMMIT DROP AS
SELECT
    c._row_num,
    NULLIF(btrim(c.customer_id), '')              AS customer_id,
    initcap(btrim(c.full_name))                   AS full_name,
    NULLIF(lower(btrim(c.email)), '')             AS email,
    CASE upper(btrim(c.country))
        WHEN 'IN' THEN 'India'          WHEN 'INDIA' THEN 'India'
        WHEN 'US' THEN 'United States'  WHEN 'USA' THEN 'United States'
        WHEN 'UNITED STATES' THEN 'United States'
        WHEN 'UK' THEN 'United Kingdom' WHEN 'GB' THEN 'United Kingdom'
        WHEN 'UNITED KINGDOM' THEN 'United Kingdom'
        WHEN 'DE' THEN 'Germany'        WHEN 'GERMANY' THEN 'Germany'
        WHEN 'CA' THEN 'Canada'         WHEN 'CANADA' THEN 'Canada'
        WHEN 'AU' THEN 'Australia'      WHEN 'AUSTRALIA' THEN 'Australia'
        ELSE initcap(btrim(c.country))
    END                                           AS country,
    ops.parse_date(c.signup_date)                 AS signup_date,
    c._batch_id,
    c._loaded_at,
    row_number() OVER (PARTITION BY NULLIF(btrim(c.customer_id), '')
                       ORDER BY c._row_num)       AS rn,
    to_jsonb(c)                                   AS payload
FROM raw.customers c;

INSERT INTO ops.quarantine (run_id, source_table, record_key, reason, payload)
SELECT %(run_id)s, 'customers', COALESCE(customer_id, 'row:' || _row_num),
       CASE WHEN customer_id IS NULL THEN 'missing_key' ELSE 'duplicate_key' END,
       payload
FROM _cust
WHERE customer_id IS NULL OR rn > 1;

CREATE TABLE staging.stg_customers AS
SELECT customer_id, full_name, email, country, signup_date, _batch_id, _loaded_at
FROM _cust
WHERE customer_id IS NOT NULL AND rn = 1;

ALTER TABLE staging.stg_customers ADD PRIMARY KEY (customer_id);
