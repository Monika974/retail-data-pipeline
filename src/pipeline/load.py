"""Load step: bulk-load validated CSVs into the raw schema with PostgreSQL COPY.

The raw layer is a full-refresh snapshot per run (TRUNCATE + COPY in one transaction), so a
failed load leaves the previous snapshot intact and re-running is always safe (idempotent).
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import Engine

from .extract import EXPECTED_SCHEMAS

log = logging.getLogger(__name__)


def load_raw(engine: Engine, raw_dir: Path, batch_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    raw_conn = engine.raw_connection()  # psycopg2 connection, needed for COPY
    try:
        with raw_conn.cursor() as cur:
            for table, columns in EXPECTED_SCHEMAS.items():
                path = raw_dir / f"{table}.csv"
                cur.execute(f"TRUNCATE raw.{table} RESTART IDENTITY")
                cols = ", ".join(columns)
                with path.open("r", encoding="utf-8", newline="") as f:
                    cur.copy_expert(
                        f"COPY raw.{table} ({cols}) FROM STDIN WITH (FORMAT csv, HEADER true)", f
                    )
                cur.execute(f"UPDATE raw.{table} SET _batch_id = %s", (batch_id,))
                cur.execute(f"SELECT count(*) FROM raw.{table}")
                counts[table] = cur.fetchone()[0]
                log.info("load    raw.%-12s rows=%d", table, counts[table])
        raw_conn.commit()  # all four tables commit together
    except Exception:
        raw_conn.rollback()
        raise
    finally:
        raw_conn.close()
    return counts
