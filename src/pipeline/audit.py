"""Run / step audit trail stored in ops.pipeline_runs and ops.pipeline_steps."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import Engine, text

log = logging.getLogger(__name__)


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]


def start_run(engine: Engine, run_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO ops.pipeline_runs (run_id) VALUES (:r)"), {"r": run_id})


def finish_run(engine: Engine, run_id: str, status: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE ops.pipeline_runs SET status = :s, finished_at = now() WHERE run_id = :r"),
            {"s": status, "r": run_id},
        )


@contextmanager
def step(engine: Engine, run_id: str, name: str) -> Iterator[dict]:
    """Time a pipeline step and record its outcome. The yielded dict lets the step report
    ``rows`` and ``message``; any exception is recorded as a failure and re-raised."""
    info: dict = {"rows": None, "message": None}
    t0 = time.perf_counter()
    status = "success"
    try:
        yield info
    except Exception as exc:
        status = "failed"
        info["message"] = f"{type(exc).__name__}: {exc}"[:2000]
        raise
    finally:
        duration = time.perf_counter() - t0
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO ops.pipeline_steps "
                    "(run_id, step, status, rows_affected, duration_s, message) "
                    "VALUES (:r, :s, :st, :n, :d, :m)"
                ),
                {
                    "r": run_id,
                    "s": name,
                    "st": status,
                    "n": info["rows"],
                    "d": round(duration, 3),
                    "m": info["message"],
                },
            )
        log.info("step %-22s %-7s %.2fs rows=%s", name, status, duration, info["rows"])
