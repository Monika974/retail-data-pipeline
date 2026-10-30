import pytest

from pipeline.extract import SchemaError, extract_all, validate_and_profile
from pipeline.generate_data import generate


def test_valid_files_are_profiled(tmp_path):
    counts = generate(tmp_path, n_orders=100, n_customers=30, seed=5)
    profiles = extract_all(tmp_path)
    assert {n: p.rows for n, p in profiles.items()} == counts
    assert len(profiles["orders"].sha256) == 64


def test_missing_file_fails(tmp_path):
    with pytest.raises(SchemaError, match="Missing source file"):
        validate_and_profile("orders", tmp_path / "orders.csv")


def test_wrong_columns_fail(tmp_path):
    (tmp_path / "orders.csv").write_text("order_id,customer\nO1,C1\n")
    with pytest.raises(SchemaError, match="do not match contract"):
        validate_and_profile("orders", tmp_path / "orders.csv")


def test_header_only_file_fails(tmp_path):
    (tmp_path / "orders.csv").write_text("order_id,customer_id,order_date,status\n")
    with pytest.raises(SchemaError, match="no rows"):
        validate_and_profile("orders", tmp_path / "orders.csv")
