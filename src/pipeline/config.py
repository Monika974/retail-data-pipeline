"""Runtime configuration, read from environment variables at call time."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_URL = "postgresql+psycopg2://pipeline:pipeline@localhost:5432/retail"


@dataclass(frozen=True)
class Settings:
    database_url: str
    raw_dir: Path
    output_dir: Path
    sql_dir: Path


def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", DEFAULT_DB_URL),
        raw_dir=Path(os.getenv("RAW_DIR", ROOT / "data" / "raw")),
        output_dir=Path(os.getenv("OUTPUT_DIR", ROOT / "output")),
        sql_dir=ROOT / "sql",
    )
