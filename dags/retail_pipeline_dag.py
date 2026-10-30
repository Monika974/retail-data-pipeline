"""Airflow DAG: the same pipeline stages as `python -m pipeline.run all`, one task per stage.

Needs apache-airflow 2.x with the `pipeline` package importable (pip install -e . or PYTHONPATH=src)
and DATABASE_URL / RAW_DIR set in the Airflow environment. Source CSVs are expected in RAW_DIR
(set generate_data=True in the `generate` task for demo runs).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.trigger_rule import TriggerRule

from pipeline import audit
from pipeline.config import get_settings
from pipeline.db import get_engine
from pipeline.extract import extract_all
from pipeline.generate_data import generate
from pipeline.load import load_raw
from pipeline.quality import run_checks
from pipeline.report import export_marts
from pipeline.transform import init_database, run_sql_dir


def _ctx():
    s = get_settings()
    return s, get_engine(s.database_url)


def t_init(run_id: str) -> None:
    s, eng = _ctx()
    init_database(eng, s.sql_dir)
    audit.start_run(eng, run_id)


def t_generate(run_id: str) -> None:
    s, eng = _ctx()
    with audit.step(eng, run_id, "generate") as st:
        st["rows"] = sum(generate(s.raw_dir).values())


def t_extract(run_id: str) -> None:
    s, eng = _ctx()
    with audit.step(eng, run_id, "extract") as st:
        st["rows"] = sum(p.rows for p in extract_all(s.raw_dir).values())


def t_load(run_id: str) -> None:
    s, eng = _ctx()
    with audit.step(eng, run_id, "load_raw") as st:
        st["rows"] = sum(load_raw(eng, s.raw_dir, batch_id=run_id).values())


def t_staging(run_id: str) -> None:
    s, eng = _ctx()
    with audit.step(eng, run_id, "transform_staging") as st:
        st["rows"] = run_sql_dir(eng, s.sql_dir / "staging", {"run_id": run_id})


def t_marts(run_id: str) -> None:
    s, eng = _ctx()
    with audit.step(eng, run_id, "transform_marts") as st:
        st["rows"] = run_sql_dir(eng, s.sql_dir / "marts", {"run_id": run_id})


def t_quality(run_id: str) -> None:
    _, eng = _ctx()
    with audit.step(eng, run_id, "data_quality") as st:
        st["rows"] = len(run_checks(eng, run_id))  # raises DataQualityError -> task fails


def t_export(run_id: str) -> None:
    s, eng = _ctx()
    with audit.step(eng, run_id, "export_marts") as st:
        st["rows"] = len(export_marts(eng, s.output_dir))


def t_finish(run_id: str, status: str) -> None:
    _, eng = _ctx()
    audit.finish_run(eng, run_id, status)


with DAG(
    dag_id="retail_data_pipeline",
    description="CSV -> raw -> staging -> marts with data-quality gates",
    start_date=datetime(2026, 1, 1),
    schedule="@daily",
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=2)},
    tags=["retail", "etl", "postgres"],
) as dag:
    RID = "{{ run_id }}"

    def task(task_id, fn, **kw):
        return PythonOperator(task_id=task_id, python_callable=fn, op_kwargs={"run_id": RID, **kw})

    init = task("init", t_init)
    generate_t = task("generate", t_generate)
    extract = task("extract", t_extract)
    load = task("load_raw", t_load)
    staging = task("transform_staging", t_staging)
    marts = task("transform_marts", t_marts)
    quality = task("data_quality", t_quality)
    export = task("export_marts", t_export)

    ok = PythonOperator(
        task_id="mark_success",
        python_callable=t_finish,
        op_kwargs={"run_id": RID, "status": "success"},
    )
    fail = PythonOperator(
        task_id="mark_failed",
        python_callable=t_finish,
        op_kwargs={"run_id": RID, "status": "failed"},
        trigger_rule=TriggerRule.ONE_FAILED,
    )

    init >> generate_t >> extract >> load >> staging >> marts >> quality >> export
    export >> ok
    [extract, load, staging, marts, quality, export] >> fail
