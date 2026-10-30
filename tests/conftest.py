import os

import pytest
from sqlalchemy import text

from pipeline.config import ROOT, Settings
from pipeline.db import get_engine

TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql+psycopg2://pipeline:pipeline@localhost:5432/retail_test"
)


@pytest.fixture()
def engine():
    """A clean PostgreSQL database for each test (skips if Postgres is unreachable).

    Only the pipeline's own schemas are dropped - point TEST_DATABASE_URL at a throwaway DB.
    """
    eng = get_engine(TEST_DB_URL)
    try:
        with eng.begin() as conn:
            for schema in ("marts", "staging", "raw", "ops"):
                conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"PostgreSQL not available for integration tests: {exc}")
    yield eng
    eng.dispose()


@pytest.fixture()
def settings(tmp_path):
    return Settings(
        database_url=TEST_DB_URL,
        raw_dir=tmp_path / "raw",
        output_dir=tmp_path / "out",
        sql_dir=ROOT / "sql",
    )
