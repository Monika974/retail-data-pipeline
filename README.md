# Retail Data Pipeline

An end-to-end batch data pipeline built on **Python + PostgreSQL**. It takes messy CSV extracts
(customers, products, orders, order items), lands them untouched in a `raw` layer, cleans and
validates them in `staging` (rejects are **quarantined with a reason, never silently dropped**),
and publishes analytics-ready dimensions, facts and aggregates in `marts` - guarded by automated
data-quality gates and a full audit trail.

```mermaid
flowchart LR
    A[CSV files<br/>data/raw] -->|schema contract<br/>+ profiling| B[extract.py]
    B -->|COPY, full refresh<br/>one transaction| C[(raw.*<br/>TEXT, as received)]
    C -->|SQL: clean, type,<br/>dedupe, validate| D[(staging.stg_*)]
    C -. rejected rows .-> Q[(ops.quarantine<br/>reason + JSON payload)]
    D -->|SQL: joins,<br/>window functions| E[(marts.*<br/>dims, fact, aggregates)]
    D --> G{{Data-quality gates<br/>error = fail run<br/>warn = log}}
    E --> G
    G -->|pass| F[CSV export<br/>Power BI / Excel]
    G -->|results| R[(ops.dq_results<br/>ops.pipeline_runs/steps)]
```

## Why it is built this way

| Decision | Reason |
|---|---|
| Raw layer is all `TEXT` | A load can never fail on a bad value; typing happens in staging where bad rows are handled explicitly. |
| Quarantine instead of delete | Every rejected row is kept with a reason (`duplicate_key`, `invalid_quantity`, `orphan_customer`, ...) so data owners can fix it at the source. |
| Row-conservation check | `raw rows = staged rows + quarantined rows` for every table, every run - proves nothing was silently lost. |
| Safe parsers (`ops.parse_date/int/num`) | Return `NULL` instead of raising, so one malformed value cannot kill the batch. Handles mixed `YYYY-MM-DD` and `DD/MM/YYYY` dates. |
| Idempotent runs | Raw is a snapshot reload (`TRUNCATE` + `COPY` in one transaction) and every staging/mart table is rebuilt, so re-running is always safe and a failed load leaves the previous data intact. |
| Severity-based DQ gates | `error` checks block publishing bad data; `warn` checks (expected defects in raw) are recorded so quality can be trended. |
| Audit trail | Every run and step (status, rows, duration, error message) is stored in `ops.pipeline_runs` / `ops.pipeline_steps`. |
| Pure SQL transforms | Logic lives in ordered, reviewable `.sql` files (`sql/staging`, `sql/marts`) - easy to port to dbt later. |

## Quick start

**Option A - Docker (Postgres + pipeline):**

```bash
docker compose up --build            # starts Postgres, runs the whole pipeline once
```

**Option B - local Python + any PostgreSQL 14+:**

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                 # then export DATABASE_URL, or keep the default
export PYTHONPATH=src
docker compose up -d db              # or point DATABASE_URL at your own Postgres
python -m pipeline.run all --orders 5000
```

Useful commands:

```bash
python -m pipeline.run generate --orders 20000   # just create sample CSVs
python -m pipeline.run all --skip-generate       # run on CSVs already in data/raw (your own data)
python -m pipeline.run transform                 # rebuild staging + marts from existing raw
python -m pipeline.run quality                   # re-run DQ checks on the latest run
python -m pipeline.run report                    # print the latest run report
make test                                        # pytest (integration tests need PostgreSQL)
```

Run the integration tests against a throw-away database (the tests drop the pipeline schemas):

```bash
export TEST_DATABASE_URL=postgresql+psycopg2://pipeline:pipeline@localhost:5432/retail_test
pytest -q
```

## Sample output (`--orders 5000`, seed 42)

```
Row counts by layer
  customers    raw=816    staged=800    quarantined=16
  products     raw=19     staged=19     quarantined=0
  orders       raw=5050   staged=4942   quarantined=108
  order_items  raw=8859   staged=8448   quarantined=411

Quarantine reasons
  customers    duplicate_key      16
  order_items  invalid_quantity   225
  order_items  orphan_order       102
  order_items  orphan_product     84
  orders       orphan_customer    58
  orders       duplicate_key      50

Data quality
  blocking checks passed: 20, failed: 0
  warnings (expected on raw data): 4
```

## Data model

| Layer | Tables |
|---|---|
| `raw` | `customers`, `products`, `orders`, `order_items` (+ `_row_num`, `_batch_id`, `_loaded_at`) |
| `staging` | `stg_customers`, `stg_products`, `stg_orders`, `stg_order_items` (typed, de-duplicated, PK/FK enforced) |
| `marts` | `dim_customers`, `dim_products`, `fct_order_items`, `mart_daily_sales` (7-day rolling revenue), `mart_monthly_revenue`, `mart_customer_rfm` (NTILE-based RFM segments), `mart_product_performance` (return rate, rank in category) |
| `ops` | `pipeline_runs`, `pipeline_steps`, `quarantine`, `dq_results` |

Revenue is counted from `completed` orders only. See [docs/data_dictionary.md](docs/data_dictionary.md).

## Data-quality checks

Defined in `src/pipeline/quality.py`; each is a SQL query returning the number of violating rows.

- **Raw (warn):** duplicate keys, missing emails, invalid quantities - profiled, then handled in staging.
- **Staging (error):** non-null keys, standardised countries, valid status values, no future dates,
  foreign keys (order -> customer, item -> order/product), positive quantities, discount in 0-100.
- **Conservation (error):** raw = staged + quarantined, per table.
- **Marts (error):** non-empty, `net <= gross`, fact row count = staging row count, daily and monthly
  revenue **reconcile** to the fact table, RFM scores within 1-5.

A failing `error` check raises `DataQualityError`, marks the run `failed` in `ops.pipeline_runs`
and exits non-zero (so schedulers and CI notice).

## Project layout

```
src/pipeline/   generate_data, extract, load, transform, quality, audit, report, run (CLI)
sql/            00_init, 01_raw_tables, staging/*.sql, marts/*.sql
dags/           Airflow DAG (one task per stage, success/failed marker tasks)
tests/          unit tests + PostgreSQL integration tests (idempotency, reconciliation, DQ gate)
.github/        CI: ruff + pytest against a Postgres service + end-to-end smoke run
```

## Using your own data

Drop CSVs with the same names and columns into `data/raw/` (the contract is in
`src/pipeline/extract.py`) and run `python -m pipeline.run all --skip-generate`. A file with
missing/renamed columns or no rows is rejected before anything is loaded.

## Power BI / Excel

Every run exports the marts to `output/*.csv`. In Power BI Desktop you can also connect directly:
**Get Data -> PostgreSQL database -> `marts` schema** (import `fct_order_items` and the two
dimensions for a star schema, or the `mart_*` tables for ready-made aggregates).

## Scheduling with Airflow

`dags/retail_pipeline_dag.py` runs the same stages as separate tasks
(`init -> generate -> extract -> load_raw -> transform_staging -> transform_marts -> data_quality
-> export_marts`) and records success/failure in `ops.pipeline_runs`. Install `apache-airflow` 2.x,
make the `pipeline` package importable, and set `DATABASE_URL`.

## Known limitations / next steps

- Raw is a full-refresh snapshot; a production version would append batches with a watermark and
  use `MERGE`/upserts into staging.
- Dates are validated by format and calendar validity but not business rules beyond "not in the future".
- Transformations are plain SQL for transparency; moving them to **dbt** (tests + docs + lineage)
  and orchestrating with Airflow/mage.ai are natural next steps.
- Add object storage (S3 / Azure Blob) as the landing zone and Grafana dashboards over `ops.*` for monitoring.
