"""Run report + CSV export of the marts (ready for Power BI / Excel)."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import Engine, text

log = logging.getLogger(__name__)

EXPORT_TABLES = [
    "dim_customers",
    "dim_products",
    "fct_order_items",
    "mart_daily_sales",
    "mart_monthly_revenue",
    "mart_customer_rfm",
    "mart_product_performance",
]


def _rows(engine: Engine, sql: str, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).fetchall()


def build_report(engine: Engine, run_id: str) -> str:
    lines = [f"\n=== Pipeline report - run {run_id} ==="]

    lines.append("\nRow counts by layer")
    for table in ["customers", "products", "orders", "order_items"]:
        raw_n = _rows(engine, f"SELECT count(*) FROM raw.{table}")[0][0]
        stg_n = _rows(engine, f"SELECT count(*) FROM staging.stg_{table}")[0][0]
        q_n = _rows(
            engine,
            "SELECT count(*) FROM ops.quarantine WHERE run_id = :r AND source_table = :t",
            r=run_id,
            t=table,
        )[0][0]
        lines.append(f"  {table:<12} raw={raw_n:<6} staged={stg_n:<6} quarantined={q_n}")

    lines.append("\nQuarantine reasons")
    for src, reason, n in _rows(
        engine,
        "SELECT source_table, reason, count(*) FROM ops.quarantine WHERE run_id = :r "
        "GROUP BY 1, 2 ORDER BY 1, 3 DESC",
        r=run_id,
    ):
        lines.append(f"  {src:<12} {reason:<18} {n}")

    dq = _rows(
        engine,
        "SELECT passed, severity, count(*) FROM ops.dq_results WHERE run_id = :r GROUP BY 1, 2",
        r=run_id,
    )
    summary = {(p, s): n for p, s, n in dq}
    lines.append("\nData quality")
    lines.append(
        f"  blocking checks passed: {summary.get((True, 'error'), 0)}, "
        f"failed: {summary.get((False, 'error'), 0)}"
    )
    lines.append(f"  warnings (expected on raw data): {summary.get((False, 'warn'), 0)}")

    lines.append("\nTop 5 products by net revenue (completed orders)")
    for name, cat, rev in _rows(
        engine,
        "SELECT product_name, category, net_revenue FROM marts.mart_product_performance "
        "ORDER BY net_revenue DESC LIMIT 5",
    ):
        lines.append(f"  {name:<30} {cat:<15} {float(rev):>12,.2f}")

    lines.append("\nCustomer segments (RFM)")
    for seg, n, rev in _rows(
        engine,
        "SELECT segment, count(*), sum(monetary) FROM marts.mart_customer_rfm "
        "GROUP BY 1 ORDER BY 3 DESC",
    ):
        lines.append(f"  {seg:<18} customers={n:<5} revenue={float(rev):>12,.2f}")
    return "\n".join(lines)


def export_marts(engine: Engine, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    raw_conn = engine.raw_connection()
    try:
        with raw_conn.cursor() as cur:
            for table in EXPORT_TABLES:
                path = out_dir / f"{table}.csv"
                with path.open("w", encoding="utf-8", newline="") as f:
                    cur.copy_expert(
                        f"COPY (SELECT * FROM marts.{table}) "
                        "TO STDOUT WITH (FORMAT csv, HEADER true)",
                        f,
                    )
                written.append(path)
        raw_conn.commit()
    finally:
        raw_conn.close()
    log.info("export  %d mart tables -> %s", len(written), out_dir)
    return written
