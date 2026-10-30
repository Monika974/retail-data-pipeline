import csv
from collections import Counter

from pipeline.generate_data import FILES, generate


def _read(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_generates_all_files_with_counts(tmp_path):
    counts = generate(tmp_path, n_orders=300, n_customers=60, seed=1)
    assert set(counts) == set(FILES)
    for name in FILES:
        assert len(_read(tmp_path / f"{name}.csv")) == counts[name] > 0


def test_same_seed_is_deterministic(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    generate(a, n_orders=200, n_customers=40, seed=7)
    generate(b, n_orders=200, n_customers=40, seed=7)
    for name in FILES:
        assert (a / f"{name}.csv").read_bytes() == (b / f"{name}.csv").read_bytes()


def test_different_seed_changes_data(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    generate(a, n_orders=200, n_customers=40, seed=1)
    generate(b, n_orders=200, n_customers=40, seed=2)
    assert (a / "orders.csv").read_bytes() != (b / "orders.csv").read_bytes()


def test_realistic_defects_are_injected(tmp_path):
    generate(tmp_path, n_orders=2000, n_customers=400, seed=3)
    customers = _read(tmp_path / "customers.csv")
    orders = _read(tmp_path / "orders.csv")
    items = _read(tmp_path / "order_items.csv")

    ids = Counter(r["customer_id"] for r in customers)
    assert any(n > 1 for n in ids.values()), "expected duplicate customers"
    assert any(r["email"] == "" for r in customers), "expected missing emails"
    assert any("/" in r["order_date"] for r in orders), "expected mixed date formats"
    assert any(r["quantity"] in ("", "0") or r["quantity"].startswith("-") for r in items)
    customer_ids = {r["customer_id"] for r in customers}
    assert any(r["customer_id"] not in customer_ids for r in orders), "expected orphan orders"
