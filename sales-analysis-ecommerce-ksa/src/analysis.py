"""End-to-end sales analysis for the (invented) Naseem online store, Saudi Arabia, 2024-2025.

Steps: load raw export -> clean (logged) -> KPIs -> trends, seasonality, categories, regions,
payments -> RFM customer segments -> repeat-purchase rate -> 3-month forecast with a holdout check
-> data-driven recommendations -> bilingual HTML report with SVG charts.

Usage:  python src/generate_data.py && python src/analysis.py
Outputs: data/orders_clean.csv, report/metrics.json, index.html
"""
import html
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "orders_raw.csv"
CLEAN = ROOT / "data" / "orders_clean.csv"
METRICS = ROOT / "report" / "metrics.json"
PAGE = ROOT / "index.html"

CITY_MAP = {
    "الرياض": "الرياض", "riyadh": "الرياض",
    "جدة": "جدة", "جده": "جدة", "jeddah": "جدة",
    "الدمام": "الدمام", "dammam": "الدمام",
    "مكة المكرمة": "مكة المكرمة", "مكة": "مكة المكرمة", "makkah": "مكة المكرمة",
    "المدينة المنورة": "المدينة المنورة", "المدينة": "المدينة المنورة", "madinah": "المدينة المنورة",
}
EVENT_WINDOWS = [
    ("رمضان ١٤٤٥", "2024-03-11", "2024-04-09"), ("الجمعة البيضاء ٢٠٢٤", "2024-11-22", "2024-12-02"),
    ("رمضان ١٤٤٦", "2025-03-01", "2025-03-29"), ("الجمعة البيضاء ٢٠٢٥", "2025-11-21", "2025-12-01"),
]
EN = {
    "عطور": "Perfumes", "عبايات": "Abayas", "العناية بالبشرة": "Skincare", "إلكترونيات صغيرة": "Small electronics",
    "مستلزمات منزلية": "Home goods", "الرياض": "Riyadh", "جدة": "Jeddah", "الدمام": "Dammam",
    "مكة المكرمة": "Makkah", "المدينة المنورة": "Madinah", "غير محدد": "Unknown",
    "رمضان ١٤٤٥": "Ramadan 2024", "الجمعة البيضاء ٢٠٢٤": "White Friday 2024",
    "رمضان ١٤٤٦": "Ramadan 2025", "الجمعة البيضاء ٢٠٢٥": "White Friday 2025",
}
MONTHS_AR = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]


# ---------------------------------------------------------------- cleaning
def clean(raw: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    log, df = [], raw.copy()

    def step(name_ar, name_en, before, after):
        log.append({"ar": name_ar, "en": name_en, "rows_removed": int(before - after), "rows_after": int(after)})

    n = len(df); df = df.drop_duplicates(); step("حذف الصفوف المكررة", "Removed exact duplicate rows", n, len(df))
    n = len(df); df = df[df["customer_id"] != "TEST"]; step("حذف طلبات الاختبار", "Removed test orders", n, len(df))
    n = len(df); df = df[df["quantity"] > 0]; step("حذف الكميات السالبة (استرجاعات مسجلة كطلبات)", "Removed negative quantities (refunds keyed as orders)", n, len(df))

    df["unit_price_sar"] = df["unit_price_sar"].astype(str).str.replace(",", "", regex=False).astype(float)
    variants = int(df["city"].dropna().nunique())
    city = df["city"].astype("string").str.strip().str.lower()
    df["city"] = city.map(CITY_MAP).fillna("غير محدد")
    unknown = int((df["city"] == "غير محدد").sum())
    log.append({"ar": f"توحيد أسماء المدن ({variants} صيغة ← ٥ مدن)، و{unknown} طلباً بلا مدينة صُنّفت «غير محدد»",
                "en": f"Unified city spellings ({variants} variants -> 5 cities); {unknown} orders without a city set to 'Unknown'",
                "rows_removed": 0, "rows_after": int(len(df))})
    missing_dd = int(df["delivery_days"].isna().sum())
    log.append({"ar": f"{missing_dd} طلباً بلا مدة توصيل استُبعدت من متوسط التوصيل فقط",
                "en": f"{missing_dd} orders missing delivery days excluded from delivery averages only",
                "rows_removed": 0, "rows_after": int(len(df))})

    df["order_datetime"] = pd.to_datetime(df["order_datetime"])
    df["date"] = df["order_datetime"].dt.normalize()
    df["month"] = df["order_datetime"].dt.to_period("M")
    df["year"] = df["order_datetime"].dt.year
    df["gross_sar"] = df["quantity"] * df["unit_price_sar"]
    df["net_sar"] = (df["gross_sar"] * (1 - df["discount_pct"])).round(2)
    df["is_returned"] = df["returned"].eq("نعم")
    df["kept_sar"] = np.where(df["is_returned"], 0.0, df["net_sar"])  # revenue after returns
    return df.reset_index(drop=True), log


# ---------------------------------------------------------------- analysis
def kpis(df: pd.DataFrame, year: int) -> dict:
    d = df[df["year"] == year]
    return {
        "revenue": round(d["kept_sar"].sum(), 0),
        "orders": int(len(d)),
        "aov": round(d["net_sar"].mean(), 1),
        "customers": int(d["customer_id"].nunique()),
        "return_rate": round(d["is_returned"].mean() * 100, 1),
        "delivery_days": round(d["delivery_days"].mean(), 1),
    }


def rfm(df: pd.DataFrame) -> pd.DataFrame:
    ref = df["date"].max() + pd.Timedelta(days=1)
    g = df.groupby("customer_id").agg(last=("date", "max"), orders=("order_id", "count"), value=("kept_sar", "sum"))
    g["recency"] = (ref - g["last"]).dt.days
    g["R"] = pd.qcut(g["recency"].rank(method="first"), 5, labels=[5, 4, 3, 2, 1]).astype(int)
    g["F"] = pd.qcut(g["orders"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    g["M"] = pd.qcut(g["value"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)

    def seg(r):
        if r.R >= 4 and r.F >= 4:
            return "الأبطال"
        if r.F >= 4:
            return "عملاء أوفياء"
        if r.R >= 4 and r.F <= 2:
            return "عملاء جدد واعدون"
        if r.R <= 2 and r.F >= 3:
            return "معرّضون للفقد"
        if r.R <= 2:
            return "خاملون"
        return "يحتاجون اهتماماً"

    g["segment"] = g.apply(seg, axis=1)
    return g


def forecast(monthly: pd.Series, horizon: int = 3) -> dict:
    """Linear trend + month-of-year seasonality. Holdout: last 3 months."""
    def design(periods, t0):
        t = np.array([(p - t0).n for p in periods])
        dummies = np.eye(12)[[p.month - 1 for p in periods]][:, 1:]
        return np.column_stack([t, dummies])

    t0 = monthly.index[0]
    train, test = monthly.iloc[:-3], monthly.iloc[-3:]
    m = LinearRegression().fit(design(train.index, t0), train.values)
    pred_test = m.predict(design(test.index, t0))
    mape = float(np.mean(np.abs(pred_test - test.values) / test.values) * 100)

    m_full = LinearRegression().fit(design(monthly.index, t0), monthly.values)
    future = pd.period_range(monthly.index[-1] + 1, periods=horizon, freq="M")
    pred = m_full.predict(design(future, t0))
    resid_sd = float(np.std(monthly.values - m_full.predict(design(monthly.index, t0)), ddof=1))
    return {
        "holdout_mape_pct": round(mape, 1),
        "holdout": [{"month": str(p), "actual": round(a), "predicted": round(f)} for p, a, f in zip(test.index, test.values, pred_test)],
        "forecast": [{"month": str(p), "value": round(v), "low": round(v - 1.28 * resid_sd), "high": round(v + 1.28 * resid_sd)}
                     for p, v in zip(future, pred)],
    }


def analyse(df: pd.DataFrame) -> dict:
    k24, k25 = kpis(df, 2024), kpis(df, 2025)
    growth = round((k25["revenue"] / k24["revenue"] - 1) * 100, 1)

    monthly = df.groupby("month")["kept_sar"].sum()

    cat = df.groupby("category").agg(revenue=("kept_sar", "sum"), orders=("order_id", "count"),
                                     return_rate=("is_returned", "mean")).sort_values("revenue", ascending=False)
    cat["share"] = cat["revenue"] / cat["revenue"].sum() * 100
    reg = df.groupby("city").agg(revenue=("kept_sar", "sum"), delivery=("delivery_days", "mean")).sort_values("revenue", ascending=False)
    reg["share"] = reg["revenue"] / reg["revenue"].sum() * 100
    pay = df.groupby("payment_method").agg(orders=("order_id", "count"), return_rate=("is_returned", "mean")).sort_values("orders", ascending=False)
    pay["share"] = pay["orders"] / pay["orders"].sum() * 100
    chan = df.groupby("channel")["kept_sar"].sum().sort_values(ascending=False)
    chan_share = (chan / chan.sum() * 100)

    daily = df.groupby("date")["kept_sar"].sum()
    events = []
    for name, s, e in EVENT_WINDOWS:
        start = pd.Timestamp(s)
        during = daily[(daily.index >= s) & (daily.index <= e)]
        # baseline = the 6 ordinary weeks right before the season (same growth level, no other event)
        before = daily[(daily.index >= start - pd.Timedelta(days=49)) & (daily.index < start - pd.Timedelta(days=7))]
        events.append({"name": name, "avg_daily": round(during.mean()), "baseline_daily": round(before.mean()),
                       "uplift_pct": round((during.mean() / before.mean() - 1) * 100)})
    normal_daily = daily.mean()

    r = rfm(df)
    seg = r.groupby("segment").agg(customers=("orders", "count"), revenue=("value", "sum"))
    seg["customer_share"] = seg["customers"] / seg["customers"].sum() * 100
    seg["revenue_share"] = seg["revenue"] / seg["revenue"].sum() * 100
    seg = seg.sort_values("revenue", ascending=False)
    repeat_rate = round((r["orders"] > 1).mean() * 100, 1)
    top20_share = round(r["value"].sort_values(ascending=False).head(int(len(r) * 0.2)).sum() / r["value"].sum() * 100, 1)

    cod = pay.loc["الدفع عند الاستلام", "return_rate"] * 100
    other_ret = df.loc[df["payment_method"] != "الدفع عند الاستلام", "is_returned"].mean() * 100
    fc = forecast(monthly)

    best_cat, worst_ret = cat.index[0], cat["return_rate"].idxmax()
    slow = reg.drop(index="غير محدد", errors="ignore")["delivery"].idxmax()
    fast = reg.drop(index="غير محدد", errors="ignore")["delivery"].idxmin()
    wf = max(events, key=lambda e: e["uplift_pct"])
    champions = seg.loc["الأبطال"] if "الأبطال" in seg.index else None
    at_risk = seg.loc["معرّضون للفقد"] if "معرّضون للفقد" in seg.index else None

    recs = [
        {"ar": f"خصّص ميزانية التسويق الأكبر لموسم {wf['name'].rsplit(' ', 1)[0]}: الإيراد اليومي فيه أعلى بنسبة {wf['uplift_pct']}٪ من الأيام العادية؛ جهّز المخزون والتوصيل قبله بأسبوعين.",
         "en": f"Put the biggest marketing budget on White Friday-type events ({EN[wf['name']]}): daily revenue runs {wf['uplift_pct']}% above normal days; stock up and add delivery capacity two weeks ahead."},
        {"ar": f"الدفع عند الاستلام يسجّل نسبة إرجاع {cod:.1f}٪ مقابل {other_ret:.1f}٪ لبقية وسائل الدفع: اعرض خصماً صغيراً للدفع المسبق (مدى / Apple Pay).",
         "en": f"Cash on delivery returns {cod:.1f}% of orders vs {other_ret:.1f}% for other methods: offer a small prepaid discount (mada / Apple Pay)."},
        {"ar": f"فئة «{worst_ret}» الأعلى إرجاعاً ({cat.loc[worst_ret, 'return_rate'] * 100:.1f}٪): أضف جدول مقاسات وصوراً أوضح لتقليل الإرجاع.",
         "en": f"'{EN[worst_ret]}' has the highest return rate ({cat.loc[worst_ret, 'return_rate'] * 100:.1f}%): add a size guide and clearer photos."},
        {"ar": f"أسرع توصيل في {fast} ({reg.loc[fast, 'delivery']:.1f} يوم) وأبطؤه في {slow} ({reg.loc[slow, 'delivery']:.1f} يوم): فاوض شركة شحن محلية في {slow}.",
         "en": f"Delivery is fastest in {EN[fast]} ({reg.loc[fast, 'delivery']:.1f} days) and slowest in {EN[slow]} ({reg.loc[slow, 'delivery']:.1f} days): negotiate a local courier for {EN[slow]}."},
    ]
    if at_risk is not None:
        recs.append({"ar": f"{int(at_risk['customers']):,} عميلاً «معرّضون للفقد» حققوا {at_risk['revenue_share']:.1f}٪ من الإيراد: أطلق حملة استعادة بكود خصم شخصي.",
                     "en": f"{int(at_risk['customers']):,} 'at risk' customers brought {at_risk['revenue_share']:.1f}% of revenue: run a win-back campaign with personal discount codes."})

    return {
        "kpi_2024": k24, "kpi_2025": k25, "revenue_growth_pct": growth,
        "monthly": [{"month": str(p), "revenue": round(v)} for p, v in monthly.items()],
        "categories": [{"name": i, "revenue": round(r_.revenue), "share": round(r_.share, 1), "return_rate": round(r_.return_rate * 100, 1)} for i, r_ in cat.iterrows()],
        "regions": [{"name": i, "revenue": round(r_.revenue), "share": round(r_.share, 1), "delivery_days": round(r_.delivery, 1)} for i, r_ in reg.iterrows()],
        "payments": [{"name": i, "share": round(r_.share, 1), "return_rate": round(r_.return_rate * 100, 1)} for i, r_ in pay.iterrows()],
        "channels": [{"name": i, "share": round(v, 1)} for i, v in chan_share.items()],
        "events": events, "normal_daily": round(normal_daily),
        "segments": [{"name": i, "customers": int(r_.customers), "customer_share": round(r_.customer_share, 1),
                      "revenue_share": round(r_.revenue_share, 1)} for i, r_ in seg.iterrows()],
        "repeat_rate": repeat_rate, "top20_share": top20_share,
        "forecast": fc, "recommendations": recs,
        "best_category": best_cat,
        "champions": None if champions is None else {"customers": int(champions["customers"]), "revenue_share": round(champions["revenue_share"], 1)},
    }


# ---------------------------------------------------------------- charts (SVG, rendered by the browser so Arabic shapes correctly)
INK, MUTED, GRID, ACCENT, ACCENT2 = "var(--ink)", "var(--muted)", "var(--grid)", "var(--accent)", "var(--accent2)"


def fmt(v: float) -> str:
    return f"{v:,.0f}"


def svg_line(points, forecast_pts, title):
    W, H, L, R, T, B = 760, 300, 64, 20, 40, 40
    vals = [p["revenue"] for p in points] + [f["high"] for f in forecast_pts]
    vmax = max(vals) * 1.08
    n = len(points) + len(forecast_pts)
    x = lambda i: L + i * (W - L - R) / (n - 1)
    y = lambda v: T + (H - T - B) * (1 - v / vmax)
    ticks = [vmax * k / 4 for k in range(5)]
    grid = "".join(f'<line x1="{L}" x2="{W - R}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="{GRID}"/>'
                   f'<text x="{L - 8}" y="{y(t) + 4:.1f}" text-anchor="end" font-size="11" fill="{MUTED}">{t / 1000:,.0f}k</text>' for t in ticks)
    path = " ".join(f'{"M" if i == 0 else "L"}{x(i):.1f},{y(p["revenue"]):.1f}' for i, p in enumerate(points))
    k0 = len(points) - 1
    fpath = f'M{x(k0):.1f},{y(points[-1]["revenue"]):.1f} ' + " ".join(f'L{x(k0 + 1 + j):.1f},{y(f["value"]):.1f}' for j, f in enumerate(forecast_pts))
    band = (f'M{x(k0):.1f},{y(points[-1]["revenue"]):.1f} ' + " ".join(f'L{x(k0 + 1 + j):.1f},{y(f["high"]):.1f}' for j, f in enumerate(forecast_pts))
            + " " + " ".join(f'L{x(k0 + 1 + j):.1f},{y(f["low"]):.1f}' for j, f in reversed(list(enumerate(forecast_pts)))) + " Z")
    labels = ""
    for i, p in enumerate(points + [{"month": f["month"]} for f in forecast_pts]):
        mth = int(p["month"][5:7])
        if mth in (1, 4, 7, 10):
            labels += f'<text x="{x(i):.1f}" y="{H - B + 18}" text-anchor="middle" font-size="11" fill="{MUTED}">{MONTHS_AR[mth - 1]} {p["month"][2:4]}</text>'
    dots = "".join(f'<circle cx="{x(i):.1f}" cy="{y(p["revenue"]):.1f}" r="2.5" fill="{ACCENT}"><title>{p["month"]}: {fmt(p["revenue"])} ر.س</title></circle>' for i, p in enumerate(points))
    return f'''<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(title)}" class="chart">
{grid}<path d="{band}" fill="{ACCENT2}" opacity="0.15"/><path d="{path}" fill="none" stroke="{ACCENT}" stroke-width="2.2"/>
<path d="{fpath}" fill="none" stroke="{ACCENT2}" stroke-width="2.2" stroke-dasharray="5 4"/>{dots}{labels}
<text x="{W - R}" y="20" text-anchor="end" font-size="12" fill="{MUTED}">ألف ر.س · الخط المتقطع = التوقع مع نطاق ٨٠٪</text></svg>'''


def svg_hbar(rows, value_key, label_fmt, title, color=ACCENT, extra=None):
    """Horizontal bars as HTML, so labels stay readable on phones (name kept for the callers)."""
    vmax = max(r[value_key] for r in rows) or 1
    out = []
    for r in rows:
        pct = 100 * r[value_key] / vmax
        note = f"<small>{html.escape(extra(r))}</small>" if extra else ""
        out.append(f'<div class="br" title="{html.escape(r["name"])}: {html.escape(label_fmt(r))}">'
                   f'<span class="bl">{html.escape(r["name"])}</span>'
                   f'<span class="bt"><i style="width:{pct:.1f}%;background:{color}"></i></span>'
                   f'<span class="bv">{html.escape(label_fmt(r))}{note}</span></div>')
    return f'<div class="bars" role="img" aria-label="{html.escape(title)}">{"".join(out)}</div>'


# ---------------------------------------------------------------- page
def build_page(m: dict, log: list, raw_rows: int, clean_rows: int) -> str:
    k24, k25 = m["kpi_2024"], m["kpi_2025"]

    def delta(a, b, lower_is_better=False, unit="٪"):
        d = (b / a - 1) * 100 if unit == "٪" else b - a
        good = (d < 0) if lower_is_better else (d > 0)
        sign = "+" if d > 0 else ""
        return f'<span class="{"up" if good else "down"}">{sign}{d:.1f}{unit if unit == "٪" else ""}</span>'

    cards = [
        ("صافي الإيراد ٢٠٢٥", "Net revenue 2025", f"{fmt(k25['revenue'])} ر.س", delta(k24["revenue"], k25["revenue"])),
        ("عدد الطلبات", "Orders", fmt(k25["orders"]), delta(k24["orders"], k25["orders"])),
        ("متوسط قيمة الطلب", "Average order value", f"{k25['aov']:,.0f} ر.س", delta(k24["aov"], k25["aov"])),
        ("العملاء", "Customers", fmt(k25["customers"]), delta(k24["customers"], k25["customers"])),
        ("نسبة الإرجاع", "Return rate", f"{k25['return_rate']}٪", delta(k24["return_rate"], k25["return_rate"], True, "pp")),
        ("متوسط التوصيل", "Avg delivery", f"{k25['delivery_days']} يوم", delta(k24["delivery_days"], k25["delivery_days"], True, "d")),
    ]
    cards_html = "".join(f'<div class="kpi"><div class="kl">{a}<small>{e}</small></div><div class="kv">{v}</div><div class="kd">{d} <small>مقارنة بـ ٢٠٢٤</small></div></div>' for a, e, v, d in cards)

    line = svg_line(m["monthly"], m["forecast"]["forecast"], "صافي الإيراد الشهري والتوقع")
    cat = svg_hbar(m["categories"], "revenue", lambda r: f'{r["share"]}٪', "الإيراد حسب الفئة", extra=lambda r: f'إرجاع {r["return_rate"]}٪')
    reg = svg_hbar(m["regions"], "revenue", lambda r: f'{r["share"]}٪', "الإيراد حسب المدينة", extra=lambda r: f'توصيل {r["delivery_days"]} يوم')
    pay = svg_hbar(m["payments"], "share", lambda r: f'{r["share"]}٪ من الطلبات', "وسائل الدفع", color=ACCENT2, extra=lambda r: f'إرجاع {r["return_rate"]}٪')
    seg_rows = [{"name": s["name"], "rs": s["revenue_share"], "cs": s["customer_share"]} for s in m["segments"]]
    seg = svg_hbar(seg_rows, "rs", lambda r: f'{r["rs"]}٪ من الإيراد', "شرائح العملاء", extra=lambda r: f'{r["cs"]}٪ من العملاء')
    ev = svg_hbar([{"name": e["name"], "u": e["uplift_pct"]} for e in m["events"]], "u", lambda r: f'+{r["u"]}٪', "أثر المواسم", color=ACCENT2)

    log_rows = "".join(f'<tr><td>{html.escape(s["ar"])}<small>{html.escape(s["en"])}</small></td><td>{s["rows_removed"] or "—"}</td><td>{fmt(s["rows_after"])}</td></tr>' for s in log)
    fc = m["forecast"]
    fc_rows = "".join(f'<tr><td>{MONTHS_AR[int(f["month"][5:7]) - 1]} {f["month"][:4]}</td><td>{fmt(f["value"])}</td><td>{fmt(f["low"])} – {fmt(f["high"])}</td></tr>' for f in fc["forecast"])
    recs = "".join(f'<li>{html.escape(r["ar"])}<small dir="ltr">{html.escape(r["en"])}</small></li>' for r in m["recommendations"])
    ch = m["champions"]

    return f"""<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>تحليل مبيعات متجر إلكتروني سعودي ٢٠٢٤–٢٠٢٥ | BahaWorks</title>
<meta name="description" content="End-to-end sales analysis of a Saudi e-commerce store: cleaning, KPIs, seasonality, RFM segments, forecast and recommendations. Demonstration project on synthetic data.">
<style>
:root{{--bg:#f6f5f1;--card:#fff;--ink:#1b1b19;--muted:#66655f;--grid:#e3e1da;--accent:#0f6e6a;--accent2:#c9741d;--up:#1d7a3f;--down:#b3412f}}
@media (prefers-color-scheme:dark){{:root{{--bg:#131312;--card:#1f1f1d;--ink:#eeede8;--muted:#a3a29b;--grid:#34342f;--accent:#3fb6ae;--accent2:#e3a056;--up:#5ccf85;--down:#f08a74}}}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 "Segoe UI",Tahoma,"Noto Sans Arabic",system-ui,sans-serif}}
main{{max-width:980px;margin:auto;padding:28px 16px 60px}}
a{{color:var(--accent)}} small{{display:block;color:var(--muted);font-size:12.5px}}
.top{{display:flex;justify-content:space-between;align-items:center;gap:12px;font-size:14px;color:var(--muted)}}
.badge{{display:inline-block;border:1px solid var(--grid);border-radius:999px;padding:2px 10px;font-size:12.5px}}
h1{{font-size:28px;line-height:1.3;margin:18px 0 4px}} h2{{font-size:20px;margin:36px 0 6px}} .lead{{font-size:17px;margin:10px 0}}
.en{{direction:ltr;text-align:left;color:var(--muted);font-size:14px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px;margin:20px 0}}
.kpi{{background:var(--card);border:1px solid var(--grid);border-radius:12px;padding:14px}} .kl{{font-size:13.5px;color:var(--muted)}}
.kv{{font-size:21px;white-space:nowrap;font-weight:700;margin:4px 0}} .kd{{font-size:13px}} .up{{color:var(--up);font-weight:600}} .down{{color:var(--down);font-weight:600}}
.card{{background:var(--card);border:1px solid var(--grid);border-radius:12px;padding:16px;margin:12px 0}}
.chart{{width:100%;height:auto;display:block;direction:ltr}}
.bars{{display:grid;gap:10px}} .br{{display:grid;grid-template-columns:8.5em 1fr 7.5em;gap:10px;align-items:center;font-size:14px}}
.bt{{height:18px;background:var(--grid);border-radius:4px;overflow:hidden}} .bt i{{display:block;height:100%;border-radius:4px}}
.bv{{font-weight:600;font-size:13.5px}} .bv small{{font-weight:400;font-size:12px}} .chart text{{font-family:inherit}}
.grid2{{display:grid;grid-template-columns:1fr;gap:12px}} @media(min-width:900px){{.grid2{{grid-template-columns:1fr 1fr}}}}
table{{width:100%;border-collapse:collapse;font-size:14px}} td,th{{padding:8px 6px;border-bottom:1px solid var(--grid);text-align:right;vertical-align:top}}
th{{color:var(--muted);font-weight:600}} ol li{{margin:0 0 12px}} ol small{{text-align:left}}
.note{{font-size:13.5px;color:var(--muted)}} footer{{margin-top:40px;border-top:1px solid var(--grid);padding-top:14px;font-size:13.5px;color:var(--muted)}}
</style></head><body><main>
<div class="top"><a href="../">← BahaWorks — معرض الأعمال</a><span class="badge">مشروع توضيحي · بيانات تجريبية</span></div>
<h1>تحليل مبيعات متجر «نسيم» الإلكتروني — السعودية ٢٠٢٤–٢٠٢٥</h1>
<p class="en">End-to-end sales analysis for an online store in Saudi Arabia · Python (pandas, scikit-learn)</p>
<p class="lead">نما صافي الإيراد بنسبة <b>{m['revenue_growth_pct']}٪</b> في ٢٠٢٥، وتصدّرت فئة «{html.escape(m['best_category'])}» المبيعات،
وحققت مواسم رمضان والجمعة البيضاء أعلى قفزات في الطلب. أكبر فرصة: تقليل الإرجاع في الدفع عند الاستلام واستعادة العملاء المعرّضين للفقد.</p>

<div class="kpis">{cards_html}</div>

<h2>الإيراد الشهري والتوقع للربع القادم</h2>
<p class="note">صافي الإيراد بعد الخصومات والإرجاعات. التوقع: نموذج اتجاه + موسمية شهرية، خطؤه على آخر ٣ أشهر محجوبة = {fc['holdout_mape_pct']}٪ (MAPE).</p>
<div class="card">{line}</div>
<div class="card"><table><tr><th>الشهر</th><th>الإيراد المتوقع (ر.س)</th><th>نطاق ٨٠٪</th></tr>{fc_rows}</table>
<p class="note">تنبيه: يبدأ رمضان ١٤٤٧ نحو ١٨ فبراير ٢٠٢٦، أي أبكر من العامين السابقين، والنموذج يعتمد على موسمية الأشهر الميلادية؛ لذا قد يكون فبراير أعلى ومارس أقل من التوقع. الحل في مشروع فعلي: إضافة متغير لأيام رمضان.</p></div>

<div class="grid2">
<div><h2>الفئات</h2><div class="card">{cat}</div></div>
<div><h2>المدن</h2><div class="card">{reg}</div></div>
</div>
<div class="grid2">
<div><h2>وسائل الدفع</h2><div class="card">{pay}</div></div>
<div><h2>أثر المواسم على الإيراد اليومي</h2><div class="card">{ev}</div><p class="note">مقارنة بمتوسط الأسابيع الستة العادية التي سبقت كل موسم، بعد الخصومات الموسمية.</p></div>
</div>

<h2>شرائح العملاء (RFM)</h2>
<p class="note">تقسيم حسب حداثة الشراء وتكراره وقيمته. {f"«الأبطال» {ch['customers']:,} عميلاً يحققون {ch['revenue_share']}٪ من الإيراد؛ " if ch else ""}
أعلى ٢٠٪ من العملاء يحققون {m['top20_share']}٪ من الإيراد، ونسبة العملاء العائدين {m['repeat_rate']}٪.</p>
<div class="card">{seg}</div>

<h2>التوصيات</h2>
<div class="card"><ol>{recs}</ol></div>

<h2>تنظيف البيانات</h2>
<p class="note">ملف التصدير الخام: {fmt(raw_rows)} صفاً ← بعد التنظيف: {fmt(clean_rows)} صفاً. كل خطوة موثقة في الكود.</p>
<div class="card"><table><tr><th>الخطوة</th><th>صفوف محذوفة</th><th>المتبقي</th></tr>{log_rows}</table></div>

<h2>المنهجية والملفات</h2>
<div class="card"><ul>
<li>Python: pandas للتنظيف والتجميع، scikit-learn للتوقع، رسوم SVG مولّدة من البيانات.</li>
<li>الملفات: <a href="data/orders_raw.csv">البيانات الخام</a> · <a href="data/orders_clean.csv">البيانات النظيفة</a> · <a href="report/metrics.json">المؤشرات (JSON)</a> · <a href="src/analysis.py">كود التحليل</a></li>
<li>التشغيل: <code dir="ltr">python src/generate_data.py && python src/analysis.py</code></li>
</ul></div>

<footer>مشروع توضيحي مبني على بيانات تجريبية لمتجر وهمي؛ أي تشابه مع متجر حقيقي غير مقصود.<br>
<span dir="ltr">Demonstration project built on synthetic data for an invented store. · BahaWorks — Bahaeldin Ali</span></footer>
</main></body></html>"""


def main():
    raw = pd.read_csv(RAW, encoding="utf-8-sig")
    df, log = clean(raw)
    m = analyse(df)
    m["cleaning_log"] = log
    m["raw_rows"], m["clean_rows"] = int(len(raw)), int(len(df))
    out = df.drop(columns=["date", "month"]).copy()
    out["order_datetime"] = out["order_datetime"].dt.strftime("%Y-%m-%d %H:%M:%S")
    out.to_csv(CLEAN, index=False, encoding="utf-8-sig")
    METRICS.parent.mkdir(exist_ok=True)
    METRICS.write_text(json.dumps(m, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    PAGE.write_text(build_page(m, log, len(raw), len(df)), encoding="utf-8")
    print(json.dumps({k: m[k] for k in ("kpi_2024", "kpi_2025", "revenue_growth_pct", "repeat_rate", "top20_share")}, ensure_ascii=False))
    print("forecast MAPE", m["forecast"]["holdout_mape_pct"], "| events", [(e["name"], e["uplift_pct"]) for e in m["events"]])


if __name__ == "__main__":
    main()
