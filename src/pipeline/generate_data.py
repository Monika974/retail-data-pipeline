"""Synthetic retail data generator.

Produces four CSV files (customers, products, orders, order_items) that mimic what a client
hands over in practice: mostly good data, with realistic problems mixed in so the pipeline's
cleaning, quarantine and data-quality logic has real work to do.

Injected defects (all deterministic for a given seed):
  * duplicate rows (same business key repeated)
  * inconsistent casing / spellings (country, category, status)
  * missing emails and quantities
  * mixed date formats (YYYY-MM-DD and DD/MM/YYYY)
  * orphan foreign keys (orders for unknown customers, items for unknown products)
  * invalid values (zero / negative quantities)
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

COUNTRIES = ["India", "United States", "United Kingdom", "Germany", "Canada", "Australia"]
COUNTRY_VARIANTS = {
    "India": ["India", "india", "IN", "India "],
    "United States": ["United States", "USA", "US", "united states"],
    "United Kingdom": ["United Kingdom", "UK", "GB"],
    "Germany": ["Germany", "germany", "DE"],
    "Canada": ["Canada", "CANADA", "CA"],
    "Australia": ["Australia", "AU"],
}
CATEGORIES = {
    "Electronics": [
        ("Wireless Mouse", 899),
        ("USB-C Hub", 1799),
        ("Bluetooth Speaker", 2499),
        ("Noise-Cancelling Headphones", 6999),
        ("Webcam HD", 3299),
    ],
    "Home & Kitchen": [
        ("Air Fryer", 5499),
        ("Electric Kettle", 1299),
        ("Mixer Grinder", 3999),
        ("Non-stick Pan Set", 2199),
    ],
    "Fashion": [
        ("Running Shoes", 3499),
        ("Denim Jacket", 2799),
        ("Cotton T-Shirt", 599),
        ("Leather Wallet", 1199),
    ],
    "Books": [
        ("Data Engineering Handbook", 899),
        ("Python Cookbook", 749),
        ("SQL Performance Explained", 649),
    ],
    "Sports": [("Yoga Mat", 999), ("Dumbbell Set", 2999), ("Cycling Gloves", 699)],
}
FIRST = [
    "Aarav",
    "Diya",
    "Rohan",
    "Sneha",
    "Kabir",
    "Meera",
    "Arjun",
    "Isha",
    "Vihaan",
    "Anaya",
    "Liam",
    "Olivia",
    "Noah",
    "Emma",
    "Lucas",
    "Mia",
    "Ethan",
    "Sofia",
    "Hans",
    "Clara",
]
LAST = [
    "Sharma",
    "Patil",
    "Iyer",
    "Khan",
    "Gupta",
    "Reddy",
    "Smith",
    "Brown",
    "Wilson",
    "Taylor",
    "Muller",
    "Schmidt",
    "Singh",
    "Joshi",
    "Nair",
]
STATUSES = [("completed", 0.82), ("cancelled", 0.08), ("returned", 0.07), ("pending", 0.03)]
STATUS_VARIANTS = {
    "completed": ["completed", "Completed", "COMPLETED"],
    "cancelled": ["cancelled", "Cancelled", "canceled"],
    "returned": ["returned", "Returned"],
    "pending": ["pending", "Pending"],
}

FILES = ("customers", "products", "orders", "order_items")


def _fmt_date(d: date, rng: random.Random, p_alt: float = 0.03) -> str:
    return d.strftime("%d/%m/%Y") if rng.random() < p_alt else d.isoformat()


def _write(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def generate(
    out_dir: Path,
    n_orders: int = 5000,
    n_customers: int = 800,
    seed: int = 42,
    end_date: date | None = None,
    days: int = 540,
) -> dict[str, int]:
    """Write the four CSVs to ``out_dir`` and return the row count of each file."""
    rng = random.Random(seed)
    end_date = end_date or date(2026, 9, 30)
    start_date = end_date - timedelta(days=days)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- products -------------------------------------------------------------------------
    products, catalog = [], []
    pid = 1
    for category, items in CATEGORIES.items():
        for name, price in items:
            product_id = f"P{pid:04d}"
            cat = (
                rng.choice([category, category.upper(), category.lower()])
                if rng.random() < 0.15
                else category
            )
            products.append([product_id, name, cat, f"{price:.2f}"])
            catalog.append((product_id, float(price)))
            pid += 1

    # ---- customers ------------------------------------------------------------------------
    customers, customer_ids = [], []
    for i in range(1, n_customers + 1):
        cid = f"C{i:05d}"
        customer_ids.append(cid)
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        email = f"{name.lower().replace(' ', '.')}{i}@example.com"
        if rng.random() < 0.05:
            email = ""  # missing email
        elif rng.random() < 0.10:
            email = email.upper()  # casing noise
        country = rng.choices(COUNTRIES, weights=[40, 25, 12, 8, 8, 7])[0]
        country = rng.choice(COUNTRY_VARIANTS[country]) if rng.random() < 0.25 else country
        signup = start_date + timedelta(days=rng.randint(0, days - 30))
        customers.append(
            [
                cid,
                name if rng.random() > 0.05 else name.lower(),
                email,
                country,
                _fmt_date(signup, rng),
            ]
        )
    for row in rng.sample(customers, k=max(1, n_customers // 50)):  # ~2% duplicates
        customers.append(list(row))

    # ---- orders + items -------------------------------------------------------------------
    orders, items = [], []
    item_seq = 1
    status_names = [s for s, _ in STATUSES]
    status_weights = [w for _, w in STATUSES]
    for i in range(1, n_orders + 1):
        oid = f"O{i:07d}"
        cid = rng.choice(customer_ids)
        if rng.random() < 0.01:
            cid = f"C9{rng.randint(1000, 9999)}"  # orphan customer
        odate = start_date + timedelta(days=rng.randint(30, days))
        status = rng.choices(status_names, weights=status_weights)[0]
        status = rng.choice(STATUS_VARIANTS[status]) if rng.random() < 0.20 else status
        orders.append([oid, cid, _fmt_date(odate, rng), status])

        for _ in range(rng.choices([1, 2, 3, 4], weights=[50, 30, 15, 5])[0]):
            product_id, price = rng.choice(catalog)
            if rng.random() < 0.01:
                product_id = f"P9{rng.randint(100, 999)}"  # orphan product
            qty = str(rng.choices([1, 2, 3, 4, 5], weights=[55, 25, 10, 6, 4])[0])
            r = rng.random()
            if r < 0.01:
                qty = str(-rng.randint(1, 3))  # invalid (negative)
            elif r < 0.015:
                qty = "0"  # invalid (zero)
            elif r < 0.025:
                qty = ""  # missing
            discount = rng.choice([0, 0, 0, 5, 10, 15, 20])
            items.append([f"OI{item_seq:08d}", oid, product_id, qty, f"{price:.2f}", discount])
            item_seq += 1
    for row in rng.sample(orders, k=max(1, n_orders // 100)):  # ~1% duplicate orders
        orders.append(list(row))

    _write(
        out_dir / "customers.csv",
        ["customer_id", "full_name", "email", "country", "signup_date"],
        customers,
    )
    _write(
        out_dir / "products.csv", ["product_id", "product_name", "category", "unit_price"], products
    )
    _write(out_dir / "orders.csv", ["order_id", "customer_id", "order_date", "status"], orders)
    _write(
        out_dir / "order_items.csv",
        ["order_item_id", "order_id", "product_id", "quantity", "unit_price", "discount_pct"],
        items,
    )
    return {
        "customers": len(customers),
        "products": len(products),
        "orders": len(orders),
        "order_items": len(items),
    }
