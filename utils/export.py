"""CSV and PDF export utilities for Finance Bot."""

import csv
import io
from datetime import datetime

from utils.i18n import cat_name, fmt_currency

_COL_HEADERS = {
    "pt": ["ID", "Data/Hora", "Tipo", "Descrição", "Valor", "Moeda", "Categoria"],
    "en": ["ID", "Date/Time", "Type", "Description", "Amount", "Currency", "Category"],
    "ja": ["ID", "日時", "タイプ", "説明", "金額", "通貨", "カテゴリ"],
}

_TYPE_LABELS = {
    "pt": {"expense": "Gasto", "income": "Ganho"},
    "en": {"expense": "Expense", "income": "Income"},
    "ja": {"expense": "支出", "income": "収入"},
}


def _tx_rows(transactions: list[dict], lang: str) -> list[list[str]]:
    """Convert transaction dicts to display rows."""
    type_map = _TYPE_LABELS.get(lang, _TYPE_LABELS["pt"])
    rows = []
    for tx in transactions:
        created = tx.get("created_at", "")
        if "T" in created:
            created = created[:16].replace("T", " ")
        rows.append([
            str(tx["id"]),
            created,
            type_map.get(tx.get("type", "expense"), tx.get("type", "")),
            tx.get("description", ""),
            str(tx.get("amount_original", 0)),
            tx.get("currency_code", "BRL"),
            cat_name(tx.get("category", "Outros"), lang),
        ])
    return rows


def generate_csv(transactions: list[dict], lang: str = "pt") -> bytes:
    """Return CSV file content as bytes."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    headers = _COL_HEADERS.get(lang, _COL_HEADERS["pt"])
    writer.writerow(headers)
    for row in _tx_rows(transactions, lang):
        writer.writerow(row)
    return buf.getvalue().encode("utf-8-sig")


def _sanitize_latin1(text: str) -> str:
    """Replace characters that can't be encoded in latin-1 for Helvetica fallback."""
    return text.encode("latin-1", errors="replace").decode("latin-1")


def generate_pdf(transactions: list[dict], lang: str = "pt", period: str = "month") -> bytes:
    """Return a simple PDF report as bytes."""
    from fpdf import FPDF

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()

    font_dir = None
    try:
        from pathlib import Path
        noto_path = Path(__file__).parent / "fonts" / "NotoSansCJKjp-Regular.ttf"
        if noto_path.exists():
            pdf.add_font("Noto", "", str(noto_path), uni=True)
            font_dir = "Noto"
    except Exception:
        pass

    if font_dir:
        pdf.set_font(font_dir, size=16)
    else:
        pdf.set_font("Helvetica", "B", 16)

    title_map = {"pt": "Relatorio Financeiro", "en": "Financial Report", "ja": "Financial Report"}
    _title = title_map.get(lang, title_map["en"])
    if not font_dir:
        _title = _sanitize_latin1(_title)
    pdf.cell(0, 12, _title, new_x="LMARGIN", new_y="NEXT", align="C")

    period_label = {"today": "Today", "week": "Week", "month": "Month"}.get(period, period)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    if font_dir:
        pdf.set_font(font_dir, size=9)
    else:
        pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, f"{period_label} - {now_str}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)

    headers = _COL_HEADERS.get(lang, _COL_HEADERS["pt"])
    col_widths = [15, 40, 25, 80, 35, 20, 50]

    def _cell(w, h, txt, **kw):
        if not font_dir:
            txt = _sanitize_latin1(txt)
        pdf.cell(w, h, txt, **kw)

    if font_dir:
        pdf.set_font(font_dir, size=9)
    else:
        pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(220, 220, 220)
    for i, h in enumerate(headers):
        _cell(col_widths[i], 7, h, border=1, fill=True, align="C")
    pdf.ln()

    if font_dir:
        pdf.set_font(font_dir, size=8)
    else:
        pdf.set_font("Helvetica", "", 8)
    rows = _tx_rows(transactions, lang)
    for row in rows:
        for i, val in enumerate(row):
            _cell(col_widths[i], 6, val[:30], border=1)
        pdf.ln()

    total_expense = sum(tx["amount_original"] for tx in transactions if tx.get("type", "expense") == "expense")
    total_income = sum(tx["amount_original"] for tx in transactions if tx.get("type") == "income")
    balance = total_income - total_expense

    pdf.ln(4)
    if font_dir:
        pdf.set_font(font_dir, size=10)
    else:
        pdf.set_font("Helvetica", "B", 10)
    summary_labels = {
        "pt": ("Gastos", "Ganhos", "Saldo"),
        "en": ("Expenses", "Income", "Balance"),
        "ja": ("Expenses", "Income", "Balance"),
    }
    exp_lbl, inc_lbl, bal_lbl = summary_labels.get(lang, summary_labels["en"])
    summary_txt = (f"{exp_lbl}: {fmt_currency(total_expense, lang)}  |  "
                   f"{inc_lbl}: {fmt_currency(total_income, lang)}  |  "
                   f"{bal_lbl}: {fmt_currency(abs(balance), lang)}")
    _cell(0, 7, summary_txt, new_x="LMARGIN", new_y="NEXT", align="C")

    return bytes(pdf.output())
