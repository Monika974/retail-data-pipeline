"""Pipeline orchestration + CLI.

python -m pipeline.run all --orders 5000        # full run: generate -> ... -> report
python -m pipeline.run all --skip-generate      # use CSVs already in data/raw
python -m pipeline.run generate --orders 20000  # just create sample data
python -m pipeline.run transform                # re-run SQL layers on existing raw data
python -m pipeline.run quality                  # re-run DQ checks only
"""

from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy import Engine

from . import audit
from .config import Settings, get_settings
from .db import get_engine
from .extract import SchemaError, extract_all
from .generate_data import generate
from .load import load_raw
from .logging_setup import setup_logging
from .quality import DataQualityError, run_checks
from .report import build_report, export_marts
from .transform import init_database, run_sql_dir

log = logging.getLogger("pipeline")


def run_pipeline(
    engine: Engine,
    settings: Settings,
    *,
    generate_data: bool = True,
    n_orders: int = 5000,
    n_customers: int = 800,
    seed: int = 42,
    export: bool = True,
) -> str:
    """Run every stage in order. Returns the run_id. Raises on any failure."""
    init_database(engine, settings.sql_dir)
    run_id = audit.new_run_id()
    audit.start_run(engine, run_id)
    log.info("=== run %s started ===", run_id)
    try:
        if generate_data:
            with audit.step(engine, run_id, "generate") as s:
                counts = generate(
                    settings.raw_dir, n_orders=n_orders, n_customers=n_customers, seed=seed
                )
                s["rows"] = sum(counts.values())
        with audit.step(engine, run_id, "extract") as s:
            profiles = extract_all(settings.raw_dir)
            s["rows"] = sum(p.rows for p in profiles.values())
        with audit.step(engine, run_id, "load_raw") as s:
            s["rows"] = sum(load_raw(engine, settings.raw_dir, batch_id=run_id).values())
        with audit.step(engine, run_id, "transform_staging") as s:
            s["rows"] = run_sql_dir(engine, settings.sql_dir / "staging", {"run_id": run_id})
        with audit.step(engine, run_id, "transform_marts") as s:
            s["rows"] = run_sql_dir(engine, settings.sql_dir / "marts", {"run_id": run_id})
        with audit.step(engine, run_id, "data_quality") as s:
            s["rows"] = len(run_checks(engine, run_id))
        if export:
            with audit.step(engine, run_id, "export_marts") as s:
                s["rows"] = len(export_marts(engine, settings.output_dir))
    except Exception:
        audit.finish_run(engine, run_id, "failed")
        log.exception("run %s FAILED", run_id)
        raise
    audit.finish_run(engine, run_id, "success")
    log.info("=== run %s succeeded ===", run_id)
    return run_id


def _latest_run_id(engine: Engine) -> str:
    with engine.connect() as conn:
        row = conn.exec_driver_sql(
            "SELECT run_id FROM ops.pipeline_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        raise SystemExit("No runs found - run `all` first.")
    return row[0]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="pipeline", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("command", choices=["all", "generate", "transform", "quality", "report"])
    p.add_argument("--orders", type=int, default=5000, help="orders to generate (default 5000)")
    p.add_argument("--customers", type=int, default=800)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--skip-generate", action="store_true", help="use CSVs already in RAW_DIR")
    p.add_argument("--no-export", action="store_true", help="skip CSV export of the marts")
    args = p.parse_args(argv)

    setup_logging()
    settings = get_settings()

    if args.command == "generate":
        counts = generate(
            settings.raw_dir, n_orders=args.orders, n_customers=args.customers, seed=args.seed
        )
        print(f"Generated into {settings.raw_dir}: {counts}")
        return 0

    engine = get_engine(settings.database_url)
    try:
        if args.command == "all":
            run_id = run_pipeline(
                engine,
                settings,
                generate_data=not args.skip_generate,
                n_orders=args.orders,
                n_customers=args.customers,
                seed=args.seed,
                export=not args.no_export,
            )
            print(build_report(engine, run_id))
        elif args.command == "transform":
            init_database(engine, settings.sql_dir)
            run_id = audit.new_run_id()
            audit.start_run(engine, run_id)
            run_sql_dir(engine, settings.sql_dir / "staging", {"run_id": run_id})
            run_sql_dir(engine, settings.sql_dir / "marts", {"run_id": run_id})
            run_checks(engine, run_id)
            audit.finish_run(engine, run_id, "success")
        elif args.command == "quality":
            run_checks(engine, _latest_run_id(engine))
        elif args.command == "report":
            print(build_report(engine, _latest_run_id(engine)))
    except (DataQualityError, SchemaError) as exc:
        log.error("%s", exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
