"""
Export service — converts query results into Excel, Image, PDF, and Word files.
"""

import io

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Twips
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

matplotlib.use("Agg")

# ── Shared helpers ─────────────────────────────────────────────

_WRAP_AT = 40  # characters before wrapping a cell value


def _truncate(val: str, limit: int = _WRAP_AT) -> str:
    return val if len(val) <= limit else val[:limit - 1] + "…"


def _col_char_widths(df: pd.DataFrame) -> list[int]:
    """Return the max character width per column (header + all values, capped at 40)."""
    widths = []
    for col in df.columns:
        col_vals = df[col].astype(str)
        max_val  = col_vals.str.len().max() if len(df) else 0
        widths.append(min(max(len(str(col)), int(max_val)), _WRAP_AT))
    return widths


# ── Excel ──────────────────────────────────────────────────────

def to_excel(df: pd.DataFrame) -> io.BytesIO:
    """Export DataFrame to Excel with auto-fitted column widths."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Results")
        ws = writer.sheets["Results"]
        for col_cells in ws.columns:
            width = max(len(str(cell.value)) if cell.value else 0 for cell in col_cells)
            ws.column_dimensions[col_cells[0].column_letter].width = width + 4
    buffer.seek(0)
    return buffer


# ── Image ──────────────────────────────────────────────────────

def to_image(df: pd.DataFrame, fmt: str = "png") -> io.BytesIO:
    """Export DataFrame as a table image (PNG or JPG) with content-fitted columns."""
    str_df  = df.astype(str).apply(lambda col: col.map(_truncate))
    n_rows  = len(str_df)
    n_cols  = len(str_df.columns)
    widths  = _col_char_widths(df)

    # Figure size: width proportional to char widths, height proportional to rows
    char_total = sum(widths)
    fig_w = max(8.0, char_total * 0.13)
    fig_h = max(1.5, n_rows * 0.32 + 1.0)

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.axis("off")

    tbl = ax.table(
        cellText=str_df.values,
        colLabels=str_df.columns.tolist(),
        cellLoc="left",
        loc="upper left",
        bbox=[0, 0, 1, 1],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)

    # Set each column width proportionally
    total_w = sum(widths)
    for col_idx, w in enumerate(widths):
        col_frac = w / total_w
        for row_idx in range(n_rows + 1):
            cell = tbl[row_idx, col_idx]
            cell.set_width(col_frac)

    # Styling
    for (row, col), cell in tbl.get_celld().items():
        cell.set_edgecolor("#e2e8f0")
        cell.set_linewidth(0.5)
        cell.PAD = 0.06
        if row == 0:
            cell.set_facecolor("#3b82f6")
            cell.set_text_props(fontweight="bold", color="white", fontsize=9)
        else:
            cell.set_facecolor("#ffffff" if row % 2 == 1 else "#f8fafc")
            cell.set_text_props(color="#1e293b", fontsize=8.5)

    fig.patch.set_facecolor("#ffffff")
    buffer = io.BytesIO()
    fig.savefig(buffer, format=fmt, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    buffer.seek(0)
    return buffer


# ── PDF ────────────────────────────────────────────────────────

def to_pdf(df: pd.DataFrame) -> io.BytesIO:
    """Export DataFrame as a formatted PDF table with content-aware column widths."""
    buffer    = io.BytesIO()
    page_size = landscape(A4) if len(df.columns) > 6 else A4
    usable_w  = page_size[0] - 60          # 30pt margins each side

    char_widths = _col_char_widths(df)
    total_chars = sum(char_widths)
    col_widths  = [usable_w * (w / total_chars) for w in char_widths]

    # Paragraph styles for wrapped cell text
    styles     = getSampleStyleSheet()
    hdr_style  = ParagraphStyle(
        "HdrCell",
        parent=styles["Normal"],
        fontSize=8,
        fontName="Helvetica-Bold",
        textColor=colors.white,
        leading=11,
        wordWrap="LTR",
    )
    cell_style = ParagraphStyle(
        "DataCell",
        parent=styles["Normal"],
        fontSize=7.5,
        fontName="Helvetica",
        textColor=colors.HexColor("#1e293b"),
        leading=10,
        wordWrap="LTR",
    )

    header_row = [Paragraph(str(c), hdr_style) for c in df.columns]
    data_rows  = [
        [Paragraph(_truncate(str(v), 60), cell_style) for v in row]
        for row in df.itertuples(index=False)
    ]
    table_data = [header_row] + data_rows

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1,
                hAlign="LEFT", splitByRow=True)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#3b82f6")),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("TOPPADDING",    (0, 0), (-1, 0),  6),
        ("BOTTOMPADDING", (0, 0), (-1, 0),  6),
        ("TOPPADDING",    (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
    ]))

    title_style = ParagraphStyle(
        "Title", parent=styles["Title"], fontSize=14,
        textColor=colors.HexColor("#1e293b"), spaceAfter=8,
    )
    doc = SimpleDocTemplate(
        buffer, pagesize=page_size,
        leftMargin=30, rightMargin=30, topMargin=30, bottomMargin=30,
    )
    doc.build([Paragraph("Query Results", title_style), Spacer(1, 10), tbl])
    buffer.seek(0)
    return buffer


# ── Word ───────────────────────────────────────────────────────

def _set_cell_bg(cell, hex_color: str) -> None:
    """Apply a background fill colour to a table cell."""
    tc_pr = cell._tc.get_or_add_tcPr()
    shd   = OxmlElement("w:shd")
    shd.set(qn("w:fill"),  hex_color)
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:val"),   "clear")
    tc_pr.append(shd)


def _set_col_width(cell, twips: int) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tcW   = OxmlElement("w:tcW")
    tcW.set(qn("w:w"),    str(twips))
    tcW.set(qn("w:type"), "dxa")
    tc_pr.append(tcW)


def to_word(df: pd.DataFrame) -> io.BytesIO:
    """Export DataFrame as a formatted Word document with fitted column widths."""
    doc = Document()

    # Page margins — narrow for more table space
    for section in doc.sections:
        section.left_margin   = Twips(720)   # 0.5 in
        section.right_margin  = Twips(720)
        section.top_margin    = Twips(720)
        section.bottom_margin = Twips(720)

    heading = doc.add_heading("Query Results", level=1)
    heading.runs[0].font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)

    char_widths = _col_char_widths(df)
    total_chars = sum(char_widths)
    # Usable page width ≈ 12240 twips (letter) minus margins (1440)
    usable_twips = 12240 - 1440
    col_twips    = [int(usable_twips * (w / total_chars)) for w in char_widths]

    tbl = doc.add_table(rows=1, cols=len(df.columns))
    tbl.style = "Table Grid"

    # Header row
    for i, col in enumerate(df.columns):
        cell = tbl.rows[0].cells[i]
        _set_cell_bg(cell, "3b82f6")
        _set_col_width(cell, col_twips[i])
        para = cell.paragraphs[0]
        para.alignment = 1          # WD_ALIGN_PARAGRAPH.CENTER
        run  = para.add_run(str(col))
        run.bold             = True
        run.font.size        = Pt(9)
        run.font.color.rgb   = RGBColor(0xFF, 0xFF, 0xFF)

    # Data rows
    for r_idx, (_, row) in enumerate(df.iterrows()):
        row_cells = tbl.add_row().cells
        bg        = "ffffff" if r_idx % 2 == 0 else "f8fafc"
        for i, val in enumerate(row):
            cell = row_cells[i]
            _set_cell_bg(cell, bg)
            _set_col_width(cell, col_twips[i])
            para = cell.paragraphs[0]
            para.alignment = 0          # LEFT
            run  = para.add_run(str(val))
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer
