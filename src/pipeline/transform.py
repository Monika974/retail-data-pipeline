"""Transform step: run the ordered SQL files for a layer, one transaction per file."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import Engine

log = logging.getLogger(__name__)


def run_sql_file(engine: Engine, path: Path, params: dict | None = None) -> None:
    sql = path.read_text(encoding="utf-8")
    with engine.begin() as conn:
        # exec_driver_sql runs multi-statement scripts and uses psycopg2 %(name)s parameters.
        # Passing no params leaves the script untouched (safe for scripts containing '%').
        conn.exec_driver_sql(sql, params) if params else conn.exec_driver_sql(sql)
    log.info("sql     %s", path.name)


def run_sql_dir(engine: Engine, directory: Path, params: dict | None = None) -> int:
    files = sorted(directory.glob("*.sql"))
    if not files:
        raise FileNotFoundError(f"No .sql files in {directory}")
    for f in files:
        run_sql_file(engine, f, params)
    return len(files)


def init_database(engine: Engine, sql_dir: Path) -> None:
    run_sql_file(engine, sql_dir / "00_init.sql")
    run_sql_file(engine, sql_dir / "01_raw_tables.sql")
