"""Extract step: validate the file contract and profile each CSV before anything is loaded.

Failing fast here (missing file, wrong columns, empty file) is cheaper and clearer than letting a
bad file reach the database.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

# The "data contract" for each source file: exact column names, in order.
EXPECTED_SCHEMAS: dict[str, list[str]] = {
    "customers": ["customer_id", "full_name", "email", "country", "signup_date"],
    "products": ["product_id", "product_name", "category", "unit_price"],
    "orders": ["order_id", "customer_id", "order_date", "status"],
    "order_items": [
        "order_item_id",
        "order_id",
        "product_id",
        "quantity",
        "unit_price",
        "discount_pct",
    ],
}


class SchemaError(Exception):
    """Raised when a source file does not match its contract."""


@dataclass
class FileProfile:
    name: str
    path: Path
    rows: int
    null_counts: dict[str, int]
    sha256: str


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_and_profile(name: str, path: Path) -> FileProfile:
    if name not in EXPECTED_SCHEMAS:
        raise SchemaError(f"Unknown source '{name}'")
    if not path.exists():
        raise SchemaError(f"Missing source file: {path}")

    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    expected = EXPECTED_SCHEMAS[name]
    if list(df.columns) != expected:
        raise SchemaError(
            f"{path.name}: columns {list(df.columns)} do not match contract {expected}"
        )
    if df.empty:
        raise SchemaError(f"{path.name}: file has a header but no rows")

    profile = FileProfile(
        name=name,
        path=path,
        rows=len(df),
        null_counts={c: int(n) for c, n in df.isna().sum().items() if n},
        sha256=_sha256(path),
    )
    log.info("extract %-12s rows=%-6d nulls=%s", name, profile.rows, profile.null_counts or "none")
    return profile


def extract_all(raw_dir: Path) -> dict[str, FileProfile]:
    return {name: validate_and_profile(name, raw_dir / f"{name}.csv") for name in EXPECTED_SCHEMAS}
