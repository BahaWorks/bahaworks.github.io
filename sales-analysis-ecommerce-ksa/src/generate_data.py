"""Generate a realistic, fully synthetic order export for an invented Saudi online store ("Naseem").

The data is deliberately messy (duplicates, mixed city spellings, missing values, test orders,
negative quantities) so the cleaning step in analysis.py has real work to do.
Seeded, so every run produces the same file.

Usage: python src/generate_data.py   ->  data/orders_raw.csv
"""
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 2026
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "orders_raw.csv"

CATEGORIES = {  # name: (share, mean price SAR, price sd, return rate)
    "عطور": (0.24, 310, 110, 0.04),
    "عبايات": (0.20, 420, 140, 0.11),
    "العناية بالبشرة": (0.22, 145, 55, 0.05),
    "إلكترونيات صغيرة": (0.14, 520, 230, 0.07),
    "مستلزمات منزلية": (0.20, 120, 50, 0.06),
}
REGIONS = {  # canonical name: (share, messy variants seen in the export)
    "الرياض": (0.36, ["الرياض", "الرياض", "الرياض", "Riyadh", "الرياض "]),
    "جدة": (0.24, ["جدة", "جدة", "جده", "Jeddah"]),
    "الدمام": (0.15, ["الدمام", "الدمام", "Dammam"]),
    "مكة المكرمة": (0.13, ["مكة المكرمة", "مكة", "Makkah"]),
    "المدينة المنورة": (0.12, ["المدينة المنورة", "المدينة", "Madinah"]),
}
CHANNELS = {"تطبيق الجوال": 0.46, "الموقع": 0.32, "سناب شات": 0.14, "انستغرام": 0.08}
PAYMENTS = {"مدى": 0.38, "Apple Pay": 0.27, "تمارا": 0.17, "الدفع عند الاستلام": 0.10, "بطاقة ائتمانية": 0.08}

# Seasonal events in 2024-2025 (approximate dates) and their demand multipliers
EVENTS = [
    ("2024-03-11", "2024-04-09", 1.55),  # Ramadan 1445
    ("2024-04-10", "2024-04-14", 1.35),  # Eid al-Fitr
    ("2024-06-15", "2024-06-19", 1.25),  # Eid al-Adha
    ("2024-09-18", "2024-09-24", 1.30),  # Saudi National Day
    ("2024-11-22", "2024-12-02", 1.90),  # White Friday
    ("2025-03-01", "2025-03-29", 1.60),  # Ramadan 1446
    ("2025-03-30", "2025-04-03", 1.40),  # Eid al-Fitr
    ("2025-06-05", "2025-06-09", 1.25),  # Eid al-Adha
    ("2025-09-18", "2025-09-24", 1.30),  # Saudi National Day
    ("2025-11-21", "2025-12-01", 2.00),  # White Friday
]


def _pick(rng, mapping, n):
    keys = list(mapping)
    p = np.array([mapping[k] if not isinstance(mapping[k], tuple) else mapping[k][0] for k in keys], float)
    return rng.choice(keys, size=n, p=p / p.sum())


def main() -> Path:
    rng = np.random.default_rng(SEED)
    days = pd.date_range("2024-01-01", "2025-12-31", freq="D")

    # daily order volume: growth trend x weekday pattern x events x noise
    t = np.arange(len(days))
    base = 14 + t * 0.012
    weekday = np.where(days.dayofweek.isin([3, 4]), 1.18, 1.0)  # Thu/Fri evenings busier
    event = np.ones(len(days))
    for start, end, mult in EVENTS:
        event[(days >= start) & (days <= end)] = mult
    daily = rng.poisson(base * weekday * event)

    dates = np.repeat(days.values, daily)
    n = len(dates)
    seconds = rng.integers(8 * 3600, 24 * 3600, n)
    ts = pd.to_datetime(dates) + pd.to_timedelta(seconds, unit="s")

    # customers: a loyal core plus a long tail of one-time buyers
    n_customers = int(n * 0.42)
    weights = rng.pareto(1.6, n_customers) + 1
    customer = rng.choice(n_customers, size=n, p=weights / weights.sum())
    customer_ids = np.array([f"C{c:05d}" for c in customer])

    cat = _pick(rng, CATEGORIES, n)
    region = _pick(rng, REGIONS, n)
    mean = np.array([CATEGORIES[c][1] for c in cat])
    sd = np.array([CATEGORIES[c][2] for c in cat])
    unit_price = np.clip(rng.normal(mean, sd), 25, None).round(2)
    qty = rng.choice([1, 1, 1, 1, 2, 2, 3], size=n)
    in_event = np.isin(pd.to_datetime(dates).normalize(), days[event > 1.2])
    discount = np.where(in_event, rng.choice([0.10, 0.15, 0.20, 0.25], n), rng.choice([0, 0, 0, 0.05, 0.10], n))
    payment = _pick(rng, PAYMENTS, n)
    # cash on delivery is refused at the door far more often
    ret_p = np.array([CATEGORIES[c][3] for c in cat]) * np.where(payment == "الدفع عند الاستلام", 2.2, 1.0)
    returned = rng.random(n) < ret_p
    delivery_days = np.clip(rng.gamma(2.2, 1.1, n) + np.where(np.isin(region, ["الرياض", "جدة"]), 0, 1.2), 1, 12).round()

    region_raw = np.array([rng.choice(REGIONS[r][1]) for r in region])

    df = pd.DataFrame({
        "order_id": [f"NS-{100000 + i}" for i in range(n)],
        "order_datetime": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "customer_id": customer_ids,
        "city": region_raw,
        "category": cat,
        "channel": _pick(rng, CHANNELS, n),
        "payment_method": payment,
        "quantity": qty,
        "unit_price_sar": unit_price,
        "discount_pct": discount,
        "returned": np.where(returned, "نعم", "لا"),
        "delivery_days": delivery_days,
    })

    # --- realistic mess -------------------------------------------------
    m = len(df)
    df.loc[rng.choice(m, 180, replace=False), "city"] = np.nan
    df.loc[rng.choice(m, 140, replace=False), "delivery_days"] = np.nan
    df.loc[rng.choice(m, 25, replace=False), "quantity"] = -1           # refunds keyed as negative orders
    test_rows = df.sample(12, random_state=SEED).assign(customer_id="TEST", unit_price_sar=1.0)
    dupes = df.sample(95, random_state=SEED + 1)                           # export duplicated some rows
    df = pd.concat([df, test_rows, dupes]).sample(frac=1, random_state=SEED).reset_index(drop=True)
    df["unit_price_sar"] = df["unit_price_sar"].map(lambda v: f"{v:,.2f}")  # prices exported as text with commas

    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False, encoding="utf-8-sig")
    return OUT


if __name__ == "__main__":
    path = main()
    print(f"wrote {path}")
