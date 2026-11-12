"""Build an interactive Arabic Excel sales dashboard (right-to-left) with live formulas.

Pick a year, city and category from the dropdowns on the dashboard sheet; every KPI, table
and chart recalculates with SUMIFS/COUNTIFS. No macros, works in Excel and LibreOffice.

Data: the synthetic Naseem store orders from ../sales-analysis-ecommerce-ksa (invented store).
Usage: python src/build_dashboard.py  ->  naseem-sales-dashboard.xlsx
"""
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, DoughnutChart, LineChart, Reference
from openpyxl.chart.label import DataLabelList


def labels(values=True, percent=False, fmt=None):
    d = DataLabelList()
    d.showVal, d.showPercent = values, percent
    d.showCatName = d.showSerName = d.showLegendKey = d.showLeaderLines = False
    if fmt:
        d.numFmt = fmt
    return d
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT.parent / "sales-analysis-ecommerce-ksa" / "data" / "orders_clean.csv"
OUT = ROOT / "naseem-sales-dashboard.xlsx"

TEAL, TEAL_LIGHT, AMBER, INK, MUTED, LINE, PAPER = "0F6E6A", "E3F1F0", "C9741D", "1B1B19", "66655F", "E3E1DA", "F6F5F1"
FONT = "Arial"
MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
CITIES = ["الرياض", "جدة", "الدمام", "مكة المكرمة", "المدينة المنورة"]
CATS = ["عطور", "عبايات", "العناية بالبشرة", "إلكترونيات صغيرة", "مستلزمات منزلية"]
PAYS = ["مدى", "Apple Pay", "تمارا", "الدفع عند الاستلام", "بطاقة ائتمانية"]

thin = Side(style="thin", color=LINE)


def f(size=11, bold=False, color=INK):
    return Font(name=FONT, size=size, bold=bold, color=color)


def build():
    df = pd.read_csv(SRC, encoding="utf-8-sig", parse_dates=["order_datetime"])
    df = df.sort_values("order_datetime").reset_index(drop=True)

    wb = Workbook()
    dash = wb.active
    dash.title = "لوحة التحكم"
    calc = wb.create_sheet("الحسابات")
    data = wb.create_sheet("البيانات")
    help_ = wb.create_sheet("طريقة الاستخدام")
    lists = wb.create_sheet("القوائم")
    for ws in (dash, calc, data, help_, lists):
        ws.sheet_view.rightToLeft = True
        ws.sheet_view.showGridLines = False

    # ------------------------------------------------------------ data sheet
    headers = ["رقم الطلب", "التاريخ", "السنة", "الشهر", "المدينة", "الفئة", "القناة", "وسيلة الدفع",
               "الكمية", "صافي القيمة (ر.س)", "مُرتجع", "الإيراد بعد الإرجاع (ر.س)", "أيام التوصيل"]
    data.append(headers)
    for r in df.itertuples(index=False):
        data.append([r.order_id, r.order_datetime.to_pydatetime(), r.order_datetime.year, r.order_datetime.month,
                     r.city, r.category, r.channel, r.payment_method, int(r.quantity), float(r.net_sar),
                     1 if r.is_returned else 0, float(r.kept_sar),
                     None if pd.isna(r.delivery_days) else float(r.delivery_days)])
    n = len(df) + 1
    for c in range(1, len(headers) + 1):
        cell = data.cell(1, c)
        cell.font, cell.fill = f(11, True, "FFFFFF"), PatternFill("solid", fgColor=TEAL)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    widths = [12, 12, 8, 7, 15, 17, 13, 18, 8, 15, 8, 20, 11]
    for i, w in enumerate(widths, 1):
        data.column_dimensions[get_column_letter(i)].width = w
    for row in data.iter_rows(min_row=2, max_row=n):
        row[1].number_format = "yyyy-mm-dd"
        row[9].number_format = row[11].number_format = "#,##0.00"
    data.freeze_panes = "A2"
    data.auto_filter.ref = f"A1:M{n}"
    data.print_area = "A1:M40"  # keeps PDF previews short

    R = lambda col: f"'البيانات'!${col}$2:${col}${n}"  # noqa: E731
    YEAR, MONTH, CITY, CAT, PAY = R("C"), R("D"), R("E"), R("F"), R("H")
    NET, RET, KEPT, DELIV = R("J"), R("K"), R("L"), R("M")

    # ------------------------------------------------------------ lists (dropdown sources)
    lists["A1"], lists["B1"], lists["C1"] = "السنة", "المدينة", "الفئة"
    for i, y in enumerate([2025, 2024], 2):
        lists.cell(i, 1, y)
    for i, v in enumerate(["الكل"] + CITIES + ["غير محدد"], 2):
        lists.cell(i, 2, v)
    for i, v in enumerate(["الكل"] + CATS, 2):
        lists.cell(i, 3, v)
    lists.sheet_state = "hidden"

    # ------------------------------------------------------------ dashboard header + selectors
    for col, w in zip("ABCDEFGHIJKLMNOPQ", [2, 16, 16, 3, 16, 16, 3, 16, 16, 3, 16, 16, 3, 16, 16, 3, 2]):
        dash.column_dimensions[col].width = w
    dash.sheet_properties.tabColor = TEAL
    for r in range(1, 70):
        for c in range(1, 18):
            dash.cell(r, c).fill = PatternFill("solid", fgColor=PAPER)

    dash.merge_cells("B2:O2")
    dash["B2"] = "لوحة مبيعات متجر «نسيم» الإلكتروني"
    dash["B2"].font = f(20, True)
    dash.merge_cells("B3:O3")
    dash["B3"] = "اختر السنة والمدينة والفئة من القوائم، وتتحدث جميع الأرقام والرسوم تلقائياً · بيانات تجريبية لمتجر وهمي"
    dash["B3"].font = f(11, color=MUTED)
    dash.row_dimensions[2].height = 34

    selectors = [("B5", "C5", "السنة", 2025, "'القوائم'!$A$2:$A$3"),
                 ("E5", "F5", "المدينة", "الكل", "'القوائم'!$B$2:$B$8"),
                 ("H5", "I5", "الفئة", "الكل", "'القوائم'!$C$2:$C$7")]
    for lab, val, text, default, src in selectors:
        dash[lab] = text
        dash[lab].font = f(11, True, MUTED)
        dash[lab].alignment = Alignment(horizontal="left", vertical="center")
        dash[val] = default
        dash[val].font = f(12, True, TEAL)
        dash[val].fill = PatternFill("solid", fgColor="FFFFFF")
        dash[val].border = Border(left=Side(style="medium", color=TEAL), right=Side(style="medium", color=TEAL),
                                  top=Side(style="medium", color=TEAL), bottom=Side(style="medium", color=TEAL))
        dash[val].alignment = Alignment(horizontal="center", vertical="center")
        dv = DataValidation(type="list", formula1=src, allow_blank=False, showDropDown=False)
        dv.error, dv.errorTitle = "اختر قيمة من القائمة", "قيمة غير صحيحة"
        dash.add_data_validation(dv)
        dv.add(dash[val])
    dash.row_dimensions[5].height = 26
    dash.merge_cells("K5:O5")
    dash["K5"] = "▼ اضغط على الخلايا ذات الإطار لاختيار القيم"
    dash["K5"].font = f(10, color=MUTED)

    SEL_Y, SEL_C, SEL_K = "'لوحة التحكم'!$C$5", "'لوحة التحكم'!$F$5", "'لوحة التحكم'!$I$5"

    # ------------------------------------------------------------ calc sheet
    calc.column_dimensions["A"].width = 26
    for c in "BCDEFG":
        calc.column_dimensions[c].width = 16
    calc["A1"], calc["A2"], calc["A3"], calc["A4"] = "معيار المدينة", "معيار الفئة", "السنة المختارة", "السنة السابقة"
    calc["B1"] = f'=IF({SEL_C}="الكل","*",{SEL_C})'
    calc["B2"] = f'=IF({SEL_K}="الكل","*",{SEL_K})'
    calc["B3"] = f"={SEL_Y}"
    calc["B4"] = "=B3-1"
    CC, CK, CY, CP = "'الحسابات'!$B$1", "'الحسابات'!$B$2", "'الحسابات'!$B$3", "'الحسابات'!$B$4"

    def crit(year_ref, extra=""):
        return f"{YEAR},{year_ref},{CITY},{CC},{CAT},{CK}{extra}"

    # KPI block rows 6-11: label | selected | previous | change
    calc["A6"], calc["B6"], calc["C6"], calc["D6"] = "المؤشر", "السنة المختارة", "السنة السابقة", "التغير"
    kpis = [
        ("صافي الإيراد (ر.س)", f"=SUMIFS({KEPT},{crit(CY)})", f"=SUMIFS({KEPT},{crit(CP)})", "#,##0"),
        ("عدد الطلبات", f"=COUNTIFS({crit(CY)})", f"=COUNTIFS({crit(CP)})", "#,##0"),
        ("متوسط قيمة الطلب (ر.س)", f"=IFERROR(SUMIFS({NET},{crit(CY)})/B8,0)", f"=IFERROR(SUMIFS({NET},{crit(CP)})/C8,0)", "#,##0"),
        ("نسبة الإرجاع", f"=IFERROR(SUMIFS({RET},{crit(CY)})/B8,0)", f"=IFERROR(SUMIFS({RET},{crit(CP)})/C8,0)", "0.0%"),
        ("متوسط أيام التوصيل", f'=IFERROR(AVERAGEIFS({DELIV},{crit(CY)},{DELIV},"<>"),0)', f'=IFERROR(AVERAGEIFS({DELIV},{crit(CP)},{DELIV},"<>"),0)', "0.0"),
    ]
    for i, (lab, cur, prev, fmt) in enumerate(kpis, 7):
        calc[f"A{i}"], calc[f"B{i}"], calc[f"C{i}"] = lab, cur, prev
        calc[f"B{i}"].number_format = calc[f"C{i}"].number_format = fmt
        if fmt == "0.0%" or fmt == "0.0":
            calc[f"D{i}"] = f'=IF($C$8=0,"—",ROUND(B{i}-C{i},{3 if fmt == "0.0%" else 1}))'  # pp / days; no prior data -> dash
            calc[f"D{i}"].number_format = '+0.0%;-0.0%;0.0%' if fmt == "0.0%" else '+0.0;-0.0;0.0'
        else:
            calc[f"D{i}"] = f'=IF(C{i}=0,"—",B{i}/C{i}-1)'
            calc[f"D{i}"].number_format = '+0.0%;-0.0%;0.0%'

    # monthly table rows 14-26
    calc["A13"], calc["B13"], calc["C13"] = "الشهر", "=\"إيراد \"&B3", "=\"إيراد \"&B4"
    for i, m in enumerate(MONTHS, 14):
        calc[f"A{i}"] = m
        calc[f"B{i}"] = f"=SUMIFS({KEPT},{crit(CY)},{MONTH},{i - 13})"
        calc[f"C{i}"] = f"=IF($C$8=0,NA(),SUMIFS({KEPT},{crit(CP)},{MONTH},{i - 13}))"  # hide the line when there is no prior year
        calc[f"B{i}"].number_format = calc[f"C{i}"].number_format = "#,##0"

    # category table rows 29-33 (ignores the category filter so all bars show)
    calc["A28"], calc["B28"] = "الفئة", "الإيراد"
    for i, c in enumerate(CATS, 29):
        calc[f"A{i}"] = c
        calc[f"B{i}"] = f"=SUMIFS({KEPT},{YEAR},{CY},{CITY},{CC},{CAT},A{i})"
        calc[f"B{i}"].number_format = "#,##0"
    # city table rows 36-40 (ignores the city filter)
    calc["A35"], calc["B35"] = "المدينة", "الإيراد"
    for i, c in enumerate(CITIES, 36):
        calc[f"A{i}"] = c
        calc[f"B{i}"] = f"=SUMIFS({KEPT},{YEAR},{CY},{CITY},A{i},{CAT},{CK})"
        calc[f"B{i}"].number_format = "#,##0"
    # payment table rows 43-47
    calc["A42"], calc["B42"], calc["C42"] = "وسيلة الدفع", "الطلبات", "نسبة الإرجاع"
    for i, p in enumerate(PAYS, 43):
        calc[f"A{i}"] = p
        calc[f"B{i}"] = f"=COUNTIFS({crit(CY)},{PAY},A{i})"
        calc[f"C{i}"] = f"=IFERROR(SUMIFS({RET},{crit(CY)},{PAY},A{i})/B{i},0)"
        calc[f"C{i}"].number_format = "0.0%"
    for r in (6, 13, 28, 35, 42):
        for c in range(1, 5):
            calc.cell(r, c).font = f(11, True, "FFFFFF")
            calc.cell(r, c).fill = PatternFill("solid", fgColor=TEAL)
    calc.sheet_properties.tabColor = AMBER

    # ------------------------------------------------------------ KPI cards on the dashboard (rows 7-10)
    cards = [("B", "C", 7), ("E", "F", 8), ("H", "I", 9), ("K", "L", 10), ("N", "O", 11)]
    for c1, c2, row in cards:
        dash.merge_cells(f"{c1}7:{c2}7"); dash.merge_cells(f"{c1}8:{c2}8"); dash.merge_cells(f"{c1}9:{c2}9")
        dash[f"{c1}7"] = f"='الحسابات'!A{row}"
        dash[f"{c1}8"] = f"='الحسابات'!B{row}"
        dash[f"{c1}9"] = f"=IF(ISNUMBER('الحسابات'!D{row}),TEXT('الحسابات'!D{row},\"{'+0.0%;-0.0%' if row in (7, 8, 9) else ('+0.0%;-0.0%' if row == 10 else '+0.0;-0.0')}\")&\" مقارنة بـ \"&'الحسابات'!$B$4,\"—\")"
        fmt = calc[f"B{row}"].number_format
        dash[f"{c1}8"].number_format = fmt
        for r, fnt in ((7, f(10.5, False, MUTED)), (8, f(22, True, INK)), (9, f(10.5, True, MUTED))):
            for col in (c1, c2):
                cell = dash[f"{col}{r}"]
                cell.fill = PatternFill("solid", fgColor="FFFFFF")
                cell.border = Border(top=thin if r == 7 else None, bottom=thin if r == 9 else None,
                                     left=thin if col == c2 else None, right=thin if col == c1 else None)
            dash[f"{c1}{r}"].font = fnt
            dash[f"{c1}{r}"].alignment = Alignment(horizontal="right", vertical="center", indent=1)
        # green/red change line: lower is better for return rate and delivery
        good = '>0' if row in (7, 8, 9) else '<0'
        bad = '<0' if row in (7, 8, 9) else '>0'
        dash.conditional_formatting.add(f"{c1}9", FormulaRule(formula=[f"AND(ISNUMBER('الحسابات'!$D${row}),'الحسابات'!$D${row}{good})"], font=Font(color="1D7A3F", bold=True)))
        dash.conditional_formatting.add(f"{c1}9", FormulaRule(formula=[f"AND(ISNUMBER('الحسابات'!$D${row}),'الحسابات'!$D${row}{bad})"], font=Font(color="B3412F", bold=True)))
    dash.row_dimensions[7].height = 22; dash.row_dimensions[8].height = 36; dash.row_dimensions[9].height = 22

    # ------------------------------------------------------------ charts
    line = LineChart()
    line.title = "الإيراد الشهري: السنة المختارة مقابل السابقة"
    line.y_axis.title = "ر.س"; line.y_axis.numFmt = "#,##0"; line.y_axis.majorGridlines = None
    line.add_data(Reference(calc, min_col=2, max_col=3, min_row=13, max_row=25), titles_from_data=True)
    line.set_categories(Reference(calc, min_col=1, min_row=14, max_row=25))
    line.series[0].graphicalProperties.line.solidFill = TEAL; line.series[0].graphicalProperties.line.width = 32000
    line.series[1].graphicalProperties.line.solidFill = "B9B7AF"; line.series[1].graphicalProperties.line.dashStyle = "dash"
    for s in line.series:
        s.smooth = False
    line.height, line.width = 8.5, 31
    line.legend.position = "b"
    dash.add_chart(line, "B12")

    bar = BarChart(); bar.type = "bar"; bar.style = 10
    bar.title = "الإيراد حسب الفئة"; bar.legend = None
    bar.add_data(Reference(calc, min_col=2, min_row=28, max_row=33), titles_from_data=True)
    bar.set_categories(Reference(calc, min_col=1, min_row=29, max_row=33))
    bar.series[0].graphicalProperties.solidFill = TEAL
    bar.x_axis.numFmt = "#,##0"; bar.y_axis.majorGridlines = None
    bar.dataLabels = labels(fmt="#,##0")
    bar.height, bar.width = 8, 15
    dash.add_chart(bar, "B30")

    bar2 = BarChart(); bar2.type = "bar"
    bar2.title = "الإيراد حسب المدينة"; bar2.legend = None
    bar2.add_data(Reference(calc, min_col=2, min_row=35, max_row=40), titles_from_data=True)
    bar2.set_categories(Reference(calc, min_col=1, min_row=36, max_row=40))
    bar2.series[0].graphicalProperties.solidFill = AMBER
    bar2.x_axis.numFmt = "#,##0"; bar2.y_axis.majorGridlines = None
    bar2.dataLabels = labels(fmt="#,##0")
    bar2.height, bar2.width = 8, 15
    dash.add_chart(bar2, "I30")

    pie = DoughnutChart()
    pie.title = "الطلبات حسب وسيلة الدفع"
    pie.add_data(Reference(calc, min_col=2, min_row=42, max_row=47), titles_from_data=True)
    pie.set_categories(Reference(calc, min_col=1, min_row=43, max_row=47))
    pie.dataLabels = labels(values=False, percent=True)
    pie.height, pie.width = 8, 15
    pie.legend.position = "r"
    dash.add_chart(pie, "B47")

    # payment return-rate mini table next to the doughnut
    dash["I48"] = "نسبة الإرجاع حسب وسيلة الدفع"; dash["I48"].font = f(12, True)
    for i, p in enumerate(PAYS, 49):
        dash[f"I{i}"] = f"='الحسابات'!A{i - 6}"
        dash[f"K{i}"] = f"='الحسابات'!C{i - 6}"
        dash[f"K{i}"].number_format = "0.0%"
        dash[f"I{i}"].font = f(11); dash[f"K{i}"].font = f(11, True)
        dash.conditional_formatting.add(f"K{i}", FormulaRule(formula=[f"K{i}>0.1"], font=Font(color="B3412F", bold=True)))
    dash["I55"] = "الأحمر: نسبة إرجاع أعلى من ١٠٪"; dash["I55"].font = f(10, color=MUTED)

    dash.print_area = "A1:P64"
    dash.page_setup.orientation = "portrait"; dash.page_setup.fitToWidth = 1; dash.page_setup.fitToHeight = 1
    dash.sheet_properties.pageSetUpPr.fitToPage = True

    # ------------------------------------------------------------ help sheet
    help_.column_dimensions["B"].width = 95
    lines = [
        ("طريقة الاستخدام", 16, True),
        ("١. افتح ورقة «لوحة التحكم» واختر السنة والمدينة والفئة من الخلايا ذات الإطار الأخضر.", 12, False),
        ("٢. تتحدث المؤشرات والرسوم فوراً عبر معادلات SUMIFS و COUNTIFS دون أي ماكرو.", 12, False),
        ("٣. لإضافة طلبات جديدة: الصقها أسفل جدول «البيانات» بنفس الأعمدة، ثم وسّع نطاق المعادلات أو حوّله إلى جدول.", 12, False),
        ("٤. ورقة «الحسابات» تعرض كل الأرقام التي تغذي اللوحة، ويمكن مراجعتها خلية بخلية.", 12, False),
        ("ملاحظة: البيانات تجريبية لمتجر وهمي لغرض العرض فقط.", 11, False),
        ("", 11, False),
        ("How to use: pick a year, city and category in the framed cells on the dashboard sheet; every KPI and chart", 11, False),
        ("recalculates with SUMIFS/COUNTIFS (no macros). Demonstration file built on synthetic data. BahaWorks — Bahaeldin Ali", 11, False),
    ]
    for i, (t, size, bold) in enumerate(lines, 2):
        help_[f"B{i}"] = t
        help_[f"B{i}"].font = f(size, bold, INK if bold else INK)
        help_[f"B{i}"].alignment = Alignment(wrap_text=True, vertical="top", horizontal="right")

    wb.active = 0
    wb.save(OUT)
    return OUT, n


if __name__ == "__main__":
    out, n = build()
    print(f"wrote {out} with {n - 1} orders")
