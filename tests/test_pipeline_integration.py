"""End-to-end tests against a real PostgreSQL (skipped automatically if none is reachable)."""

import pytest
from sqlalchemy import text

from pipeline.extract import SchemaError
from pipeline.quality import DataQualityError, run_checks
from pipeline.run import run_pipeline

SMALL = dict(n_orders=800, n_customers=150, seed=11, export=False)


def column(engine, sql, **params):
    with engine.connect() as conn:
        return {row[0] for row in conn.execute(text(sql), params)}


def scalar(engine, sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()


def test_full_run_succeeds_and_records_audit(engine, settings):
    run_id = run_pipeline(engine, settings, **SMALL)
    assert (
        scalar(engine, "SELECT status FROM ops.pipeline_runs WHERE run_id = :r", r=run_id)
        == "success"
    )
    steps = scalar(engine, "SELECT count(*) FROM ops.pipeline_steps WHERE run_id = :r", r=run_id)
    assert steps == 6  # generate, extract, load, staging, marts, DQ (export disabled)


def test_every_raw_row_is_staged_or_quarantined(engine, settings):
    run_id = run_pipeline(engine, settings, **SMALL)
    for table, stg in [
        ("customers", "stg_customers"),
        ("products", "stg_products"),
        ("orders", "stg_orders"),
        ("order_items", "stg_order_items"),
    ]:
        raw_n = scalar(engine, f"SELECT count(*) FROM raw.{table}")
        stg_n = scalar(engine, f"SELECT count(*) FROM staging.{stg}")
        q_n = scalar(
            engine,
            "SELECT count(*) FROM ops.quarantine WHERE run_id = :r AND source_table = :t",
            r=run_id,
            t=table,
        )
        assert raw_n == stg_n + q_n, table


def test_dirty_data_is_cleaned_and_quarantined(engine, settings):
    run_id = run_pipeline(engine, settings, **SMALL)
    reasons = column(
        engine, "SELECT DISTINCT reason FROM ops.quarantine WHERE run_id = :r", r=run_id
    )
    assert {"duplicate_key", "invalid_quantity"} <= reasons
    countries = column(engine, "SELECT DISTINCT country FROM staging.stg_customers")
    assert countries <= {
        "India",
        "United States",
        "United Kingdom",
        "Germany",
        "Canada",
        "Australia",
    }
    assert (
        scalar(
            engine,
            "SELECT count(*) FROM staging.stg_orders "
            "WHERE status NOT IN ('completed','cancelled','returned','pending')",
        )
        == 0
    )


def test_rerun_is_idempotent(engine, settings):
    run_pipeline(engine, settings, **SMALL)
    first = (
        scalar(engine, "SELECT count(*) FROM staging.stg_order_items"),
        scalar(engine, "SELECT sum(net_amount) FROM marts.fct_order_items"),
    )
    run_pipeline(engine, settings, generate_data=False, export=False)
    second = (
        scalar(engine, "SELECT count(*) FROM staging.stg_order_items"),
        scalar(engine, "SELECT sum(net_amount) FROM marts.fct_order_items"),
    )
    assert first == second
    assert scalar(engine, "SELECT count(*) FROM raw.orders") == scalar(
        engine, "SELECT count(*) FROM raw.orders WHERE _batch_id IS NOT NULL"
    )


def test_marts_reconcile(engine, settings):
    run_pipeline(engine, settings, **SMALL)
    fact = scalar(
        engine, "SELECT sum(net_amount) FROM marts.fct_order_items WHERE order_status = 'completed'"
    )
    daily = scalar(engine, "SELECT sum(net_revenue) FROM marts.mart_daily_sales")
    monthly = scalar(engine, "SELECT sum(net_revenue) FROM marts.mart_monthly_revenue")
    assert fact == daily == monthly


def test_quality_gate_blocks_bad_data(engine, settings):
    run_id = run_pipeline(engine, settings, **SMALL)
    with engine.begin() as conn:  # simulate a regression that lets a bad row through
        conn.execute(
            text(
                "UPDATE staging.stg_order_items SET quantity = -1 "
                "WHERE order_item_id = (SELECT min(order_item_id) "
                "FROM staging.stg_order_items)"
            )
        )
    with pytest.raises(DataQualityError, match="positive_quantity"):
        run_checks(engine, run_id)


def test_bad_source_file_fails_the_run_cleanly(engine, settings):
    run_pipeline(engine, settings, **SMALL)
    (settings.raw_dir / "orders.csv").write_text("order_id,customer\nO1,C1\n")
    with pytest.raises(SchemaError):
        run_pipeline(engine, settings, generate_data=False, export=False)
    assert (
        scalar(engine, "SELECT status FROM ops.pipeline_runs ORDER BY started_at DESC LIMIT 1")
        == "failed"
    )
    # previous good data must still be intact
    assert scalar(engine, "SELECT count(*) FROM marts.fct_order_items") > 0
