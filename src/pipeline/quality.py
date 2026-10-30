"""Data-quality gates.

Each check is a SQL query that returns the NUMBER OF VIOLATING ROWS (0 = pass).
  * severity "error" -> pipeline fails (bad data must never reach the marts)
  * severity "warn"  -> logged and stored, pipeline continues (expected on raw data; staging
                        cleans or quarantines it)
Results are persisted to ops.dq_results so quality can be trended over time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import Engine

log = logging.getLogger(__name__)


class DataQualityError(Exception):
    def __init__(self, failures: list[CheckResult]):
        self.failures = failures
        names = ", ".join(f"{f.table}.{f.name}={f.violations}" for f in failures)
        super().__init__(f"{len(failures)} blocking data-quality check(s) failed: {names}")


@dataclass(frozen=True)
class Check:
    name: str
    table: str
    severity: str
    sql: str


@dataclass(frozen=True)
class CheckResult:
    name: str
    table: str
    severity: str
    violations: int

    @property
    def passed(self) -> bool:
        return self.violations == 0


def _conservation(table: str, stg: str) -> Check:
    """Every raw row must end up in staging OR quarantine for this run - nothing silently lost."""
    return Check(
        f"row_conservation_{table}",
        f"raw.{table}",
        "error",
        f"""SELECT ABS((SELECT count(*) FROM raw.{table})
                     - (SELECT count(*) FROM staging.{stg})
                     - (SELECT count(*) FROM ops.quarantine
                        WHERE run_id = %(run_id)s AND source_table = '{table}'))""",
    )


CHECKS: list[Check] = [
    # ---- raw layer: profiling only (these defects are EXPECTED and handled in staging) -------
    Check(
        "duplicate_customer_ids",
        "raw.customers",
        "warn",
        "SELECT count(*) - count(DISTINCT customer_id) FROM raw.customers",
    ),
    Check(
        "missing_email",
        "raw.customers",
        "warn",
        "SELECT count(*) FROM raw.customers WHERE email IS NULL OR btrim(email) = ''",
    ),
    Check(
        "duplicate_order_ids",
        "raw.orders",
        "warn",
        "SELECT count(*) - count(DISTINCT order_id) FROM raw.orders",
    ),
    Check(
        "non_positive_or_null_quantity",
        "raw.order_items",
        "warn",
        "SELECT count(*) FROM raw.order_items "
        "WHERE ops.parse_int(quantity) IS NULL OR ops.parse_int(quantity) <= 0",
    ),
    # ---- staging layer: hard gates ------------------------------------------------------------
    Check(
        "pk_not_null",
        "staging.stg_customers",
        "error",
        "SELECT count(*) FROM staging.stg_customers WHERE customer_id IS NULL",
    ),
    Check(
        "email_format",
        "staging.stg_customers",
        "warn",
        "SELECT count(*) FROM staging.stg_customers "
        "WHERE email IS NOT NULL AND email !~ '^[^@ ]+@[^@ ]+[.][^@ ]+$'",
    ),
    Check(
        "country_standardised",
        "staging.stg_customers",
        "error",
        "SELECT count(*) FROM staging.stg_customers WHERE country <> initcap(country) "
        "OR country IN ('IN', 'US', 'UK', 'GB', 'USA')",
    ),
    Check(
        "valid_status",
        "staging.stg_orders",
        "error",
        "SELECT count(*) FROM staging.stg_orders "
        "WHERE status NOT IN ('completed', 'cancelled', 'returned', 'pending')",
    ),
    Check(
        "order_date_not_null",
        "staging.stg_orders",
        "error",
        "SELECT count(*) FROM staging.stg_orders WHERE order_date IS NULL",
    ),
    Check(
        "no_future_orders",
        "staging.stg_orders",
        "error",
        "SELECT count(*) FROM staging.stg_orders WHERE order_date > current_date",
    ),
    Check(
        "customer_fk",
        "staging.stg_orders",
        "error",
        "SELECT count(*) FROM staging.stg_orders o "
        "LEFT JOIN staging.stg_customers c USING (customer_id) WHERE c.customer_id IS NULL",
    ),
    Check(
        "positive_quantity",
        "staging.stg_order_items",
        "error",
        "SELECT count(*) FROM staging.stg_order_items WHERE quantity IS NULL OR quantity <= 0",
    ),
    Check(
        "discount_in_range",
        "staging.stg_order_items",
        "error",
        "SELECT count(*) FROM staging.stg_order_items WHERE discount_pct < 0 OR discount_pct > 100",
    ),
    Check(
        "order_fk",
        "staging.stg_order_items",
        "error",
        "SELECT count(*) FROM staging.stg_order_items i "
        "LEFT JOIN staging.stg_orders o USING (order_id) WHERE o.order_id IS NULL",
    ),
    Check(
        "product_fk",
        "staging.stg_order_items",
        "error",
        "SELECT count(*) FROM staging.stg_order_items i "
        "LEFT JOIN staging.stg_products p USING (product_id) WHERE p.product_id IS NULL",
    ),
    _conservation("customers", "stg_customers"),
    _conservation("products", "stg_products"),
    _conservation("orders", "stg_orders"),
    _conservation("order_items", "stg_order_items"),
    # ---- marts layer: business-logic + reconciliation ----------------------------------------
    Check(
        "marts_not_empty",
        "marts.fct_order_items",
        "error",
        "SELECT CASE WHEN count(*) = 0 THEN 1 ELSE 0 END FROM marts.fct_order_items",
    ),
    Check(
        "net_not_above_gross",
        "marts.fct_order_items",
        "error",
        "SELECT count(*) FROM marts.fct_order_items "
        "WHERE net_amount > gross_amount OR net_amount < 0",
    ),
    Check(
        "fact_rowcount_matches_staging",
        "marts.fct_order_items",
        "error",
        "SELECT ABS((SELECT count(*) FROM marts.fct_order_items) "
        "- (SELECT count(*) FROM staging.stg_order_items))",
    ),
    Check(
        "daily_sales_reconciles_to_fact",
        "marts.mart_daily_sales",
        "error",
        "SELECT CASE WHEN ABS(COALESCE((SELECT sum(net_revenue) FROM marts.mart_daily_sales), 0)"
        " - COALESCE((SELECT sum(net_amount) FROM marts.fct_order_items"
        "             WHERE order_status = 'completed'), 0)) > 0.01 THEN 1 ELSE 0 END",
    ),
    Check(
        "monthly_revenue_reconciles_to_fact",
        "marts.mart_monthly_revenue",
        "error",
        "SELECT CASE WHEN ABS(COALESCE((SELECT sum(net_revenue) "
        "FROM marts.mart_monthly_revenue), 0)"
        " - COALESCE((SELECT sum(net_amount) FROM marts.fct_order_items"
        "             WHERE order_status = 'completed'), 0)) > 0.01 THEN 1 ELSE 0 END",
    ),
    Check(
        "rfm_scores_in_range",
        "marts.mart_customer_rfm",
        "error",
        "SELECT count(*) FROM marts.mart_customer_rfm "
        "WHERE r_score NOT BETWEEN 1 AND 5 OR f_score NOT BETWEEN 1 AND 5 "
        "OR m_score NOT BETWEEN 1 AND 5",
    ),
]


def run_checks(
    engine: Engine, run_id: str, checks: list[Check] | None = None, raise_on_error: bool = True
) -> list[CheckResult]:
    results: list[CheckResult] = []
    raw_conn = engine.raw_connection()
    try:
        with raw_conn.cursor() as cur:
            for chk in checks or CHECKS:
                cur.execute(chk.sql, {"run_id": run_id})
                violations = int(cur.fetchone()[0])
                res = CheckResult(chk.name, chk.table, chk.severity, violations)
                results.append(res)
                cur.execute(
                    "INSERT INTO ops.dq_results "
                    "(run_id, check_name, table_name, severity, violations, passed) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (run_id, res.name, res.table, res.severity, res.violations, res.passed),
                )
                level = (
                    logging.INFO
                    if res.passed
                    else (logging.ERROR if res.severity == "error" else logging.WARNING)
                )
                log.log(
                    level,
                    "dq %-5s %-34s %-26s violations=%d",
                    "PASS" if res.passed else "FAIL",
                    res.name,
                    res.table,
                    res.violations,
                )
        raw_conn.commit()
    finally:
        raw_conn.close()

    failures = [r for r in results if not r.passed and r.severity == "error"]
    if failures and raise_on_error:
        raise DataQualityError(failures)
    return results
