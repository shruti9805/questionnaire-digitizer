"""Export a reviewed response to an Excel workbook.

All content (demographics, per-item Likert responses, the wide one-row-per-
respondent table, and the extraction method notes) lives on a single sheet,
stacked in sections with a bold section title and a blank row between each,
rather than as separate sheet tabs (changed 2026-09-15 at user request - see
PLAN.md changelog; each section's own columns/headers/values/formatting are
unchanged from the original per-sheet version, only the destination and
starting row changed). Detection/parsing logic (checkbox_pipeline.py,
parse_docx.py) is untouched by this file.
"""
from __future__ import annotations

from io import BytesIO

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from db import get_demo_fields, get_items, get_response_demo_values, get_response_items, list_responses

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(bold=True, color="FFFFFF")
SECTION_FONT = Font(bold=True, size=13)
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
SCALE_LABEL = {1: "Strongly Disagree", 2: "Disagree", 3: "Neither Agree nor Disagree",
               4: "Agree", 5: "Strongly Agree", None: "(blank)"}


def _header_row(ws, row_idx, headers):
    for j, h in enumerate(headers, start=1):
        cell = ws.cell(row=row_idx, column=j, value=h)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL


def _section_title(ws, row_idx, title):
    cell = ws.cell(row=row_idx, column=1, value=title)
    cell.font = SECTION_FONT


def _widen(ws, col_idx, width):
    """Set a column's width to `width` unless it's already wider (so
    multiple sections sharing a column each get enough room for their own
    content, without one section's narrower request shrinking another's)."""
    letter = get_column_letter(col_idx)
    current = ws.column_dimensions[letter].width
    if not current or width > current:
        ws.column_dimensions[letter].width = width


METHOD_NOTE = (
    "Pages rendered at 300 DPI (pdftoppm). Likert checkbox values (1-5) detected by: "
    "(1) locating the 5 answer-column gridlines via longest-contiguous-dark-run projection, "
    "(2) isolating handwritten ink via a per-document Otsu threshold on HSV saturation "
    "(pen-color-agnostic, not hardcoded to any specific ink color), (3) clustering ink "
    "pixels into one mark per answered row and binning by column, (4) reconciling the total "
    "detected count against this phase's known item count before trusting any alignment."
)
DEMO_NOTE = (
    "Not automatically read in this version (no handwriting/OCR recognition) - entered "
    "manually by the researcher while viewing the scanned page(s)."
)


def build_workbook(phase_id: int, phase_name: str, source_pdf_filename: str, response_id: int) -> openpyxl.Workbook:
    demo_fields = get_demo_fields(phase_id)
    demo_values = get_response_demo_values(response_id)
    items = get_items(phase_id)
    response_items = {ri["item_id"]: ri for ri in get_response_items(response_id)}

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Response"
    row = 1

    # ---------- Demographics ----------
    _section_title(ws, row, "Demographics")
    row += 1
    _header_row(ws, row, ["Field", "Value"])
    row += 1
    for df in demo_fields:
        c1 = ws.cell(row=row, column=1, value=df["label_en"])
        c1.border = BORDER
        c1.alignment = Alignment(wrap_text=True, vertical="top")
        c2 = ws.cell(row=row, column=2, value=demo_values.get(df["id"], ""))
        c2.border = BORDER
        c2.alignment = Alignment(wrap_text=True, vertical="top")
        row += 1
    _widen(ws, 1, 45)
    _widen(ws, 2, 55)
    row += 1

    # ---------- Likert_Responses (long format) ----------
    _section_title(ws, row, "Likert Responses")
    row += 1
    _header_row(ws, row, ["Sr.No", "Code", "Statement (English)", "Response (1-5)", "Confidence", "Note"])
    row += 1
    for it in items:
        ri = response_items.get(it["id"])
        value = ri["value"] if ri else None
        confidence = ri["confidence"] if ri else "missing"
        note = ri["note"] if ri else "no detection recorded for this item"
        ws.cell(row=row, column=1, value=it["position"]).border = BORDER
        ws.cell(row=row, column=2, value=it["code"]).border = BORDER
        c3 = ws.cell(row=row, column=3, value=it["statement_en"])
        c3.border = BORDER
        c3.alignment = Alignment(wrap_text=True, vertical="top")
        vcell = ws.cell(row=row, column=4, value=value)
        vcell.border = BORDER
        vcell.alignment = Alignment(horizontal="center")
        ws.cell(row=row, column=5, value=confidence).border = BORDER
        c6 = ws.cell(row=row, column=6, value=note)
        c6.border = BORDER
        c6.alignment = Alignment(wrap_text=True, vertical="top")
        row += 1
    _widen(ws, 1, 8)
    _widen(ws, 2, 10)
    _widen(ws, 3, 80)
    _widen(ws, 4, 14)
    _widen(ws, 5, 12)
    _widen(ws, 6, 45)
    row += 1

    # ---------- Wide_Format (one row per respondent) ----------
    _section_title(ws, row, "Wide Format")
    row += 1
    demo_headers = [df["label_en"] for df in demo_fields]
    item_headers = [it["code"] for it in items]
    headers = ["Respondent_File"] + demo_headers + item_headers
    _header_row(ws, row, headers)
    row += 1
    row_values = [source_pdf_filename]
    row_values += [demo_values.get(df["id"], "") for df in demo_fields]
    for it in items:
        ri = response_items.get(it["id"])
        row_values.append(ri["value"] if ri else None)
    for j, val in enumerate(row_values, start=1):
        ws.cell(row=row, column=j, value=val).border = BORDER
    for j in range(1, len(headers) + 1):
        _widen(ws, j, 14)
    row += 2

    # ---------- Extraction_Notes ----------
    _section_title(ws, row, "Extraction Notes")
    row += 1
    flagged = [ri for ri in response_items.values() if ri["confidence"] != "ok"]
    notes = [
        ("Phase", f"{phase_name} (id {phase_id})"),
        ("Source PDF", source_pdf_filename),
        ("Method", METHOD_NOTE),
        ("Demographic fields", DEMO_NOTE),
        ("Flagged for review", f"{len(flagged)} of {len(items)} items were flagged as low-confidence or "
                                f"conflicting during automated detection (see below) and required a human "
                                f"confirm/correct pass before this export."),
    ]
    for k, v in notes:
        c1 = ws.cell(row=row, column=1, value=k)
        c1.font = Font(bold=True)
        c1.alignment = Alignment(wrap_text=True, vertical="top")
        c2 = ws.cell(row=row, column=2, value=v)
        c2.alignment = Alignment(wrap_text=True, vertical="top")
        row += 1
    row += 1
    if flagged:
        ws.cell(row=row, column=1, value="Flagged items (resolved before export)").font = Font(bold=True)
        row += 1
        _header_row(ws, row, ["Code", "Value", "Confidence", "Note"])
        row += 1
        code_by_item_id = {it["id"]: it["code"] for it in items}
        for ri in sorted(flagged, key=lambda r: r["item_id"]):
            ws.cell(row=row, column=1, value=code_by_item_id.get(ri["item_id"], "?")).border = BORDER
            ws.cell(row=row, column=2, value=ri["value"]).border = BORDER
            ws.cell(row=row, column=3, value=ri["confidence"]).border = BORDER
            note_cell = ws.cell(row=row, column=4, value=ri["note"])
            note_cell.border = BORDER
            note_cell.alignment = Alignment(wrap_text=True, vertical="top")
            row += 1

    return wb


def export_response_to_bytes(phase_id: int, phase_name: str, source_pdf_filename: str, response_id: int) -> bytes:
    wb = build_workbook(phase_id, phase_name, source_pdf_filename, response_id)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_batch_workbook(phase_id: int, phase_name: str, batch_id: int) -> openpyxl.Workbook:
    """Same sections as build_workbook, generalized to N respondents
    (Demographics and Wide_Format each get one row per respondent instead of
    one row per field; Likert_Responses gains a Respondent column), all
    stacked on one sheet as with the single-response export."""
    demo_fields = get_demo_fields(phase_id)
    items = get_items(phase_id)
    responses = list_responses(batch_id)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Response"
    row = 1

    def respondent_name(r):
        return r["respondent_label"] or r["source_pdf_filename"]

    # ---------- Demographics (one row per respondent) ----------
    _section_title(ws, row, "Demographics")
    row += 1
    _header_row(ws, row, ["Respondent"] + [df["label_en"] for df in demo_fields])
    row += 1
    for r in responses:
        demo_values = get_response_demo_values(r["id"])
        ws.cell(row=row, column=1, value=respondent_name(r)).border = BORDER
        for j, df in enumerate(demo_fields, start=2):
            ws.cell(row=row, column=j, value=demo_values.get(df["id"], "")).border = BORDER
        row += 1
    _widen(ws, 1, 30)
    for j in range(2, len(demo_fields) + 2):
        _widen(ws, j, 30)
    row += 1

    # ---------- Likert_Responses (long format, all respondents) ----------
    _section_title(ws, row, "Likert Responses")
    row += 1
    _header_row(ws, row, ["Respondent", "Sr.No", "Code", "Statement (English)", "Response (1-5)", "Confidence", "Note"])
    row += 1
    for r in responses:
        response_items = {ri["item_id"]: ri for ri in get_response_items(r["id"])}
        for it in items:
            ri = response_items.get(it["id"])
            value = ri["value"] if ri else None
            confidence = ri["confidence"] if ri else "missing"
            note = ri["note"] if ri else "no detection recorded for this item"
            ws.cell(row=row, column=1, value=respondent_name(r)).border = BORDER
            ws.cell(row=row, column=2, value=it["position"]).border = BORDER
            ws.cell(row=row, column=3, value=it["code"]).border = BORDER
            c4 = ws.cell(row=row, column=4, value=it["statement_en"])
            c4.border = BORDER
            c4.alignment = Alignment(wrap_text=True, vertical="top")
            vcell = ws.cell(row=row, column=5, value=value)
            vcell.border = BORDER
            vcell.alignment = Alignment(horizontal="center")
            ws.cell(row=row, column=6, value=confidence).border = BORDER
            c7 = ws.cell(row=row, column=7, value=note)
            c7.border = BORDER
            c7.alignment = Alignment(wrap_text=True, vertical="top")
            row += 1
    _widen(ws, 1, 20)
    _widen(ws, 2, 8)
    _widen(ws, 3, 10)
    _widen(ws, 4, 70)
    _widen(ws, 5, 14)
    _widen(ws, 6, 12)
    _widen(ws, 7, 45)
    row += 1

    # ---------- Wide_Format (one row per respondent) ----------
    _section_title(ws, row, "Wide Format")
    row += 1
    demo_headers = [df["label_en"] for df in demo_fields]
    item_headers = [it["code"] for it in items]
    headers = ["Respondent_File"] + demo_headers + item_headers
    _header_row(ws, row, headers)
    row += 1
    for r in responses:
        demo_values = get_response_demo_values(r["id"])
        response_items = {ri["item_id"]: ri for ri in get_response_items(r["id"])}
        row_values = [respondent_name(r)]
        row_values += [demo_values.get(df["id"], "") for df in demo_fields]
        for it in items:
            ri = response_items.get(it["id"])
            row_values.append(ri["value"] if ri else None)
        for j, val in enumerate(row_values, start=1):
            ws.cell(row=row, column=j, value=val).border = BORDER
        row += 1
    for j in range(1, len(headers) + 1):
        _widen(ws, j, 14)
    row += 1

    # ---------- Extraction_Notes ----------
    _section_title(ws, row, "Extraction Notes")
    row += 1
    notes = [
        ("Phase", f"{phase_name} (id {phase_id})"),
        ("Batch", f"batch id {batch_id}, {len(responses)} respondent(s)"),
        ("Method", METHOD_NOTE),
        ("Demographic fields", DEMO_NOTE),
    ]
    for k, v in notes:
        c1 = ws.cell(row=row, column=1, value=k)
        c1.font = Font(bold=True)
        c1.alignment = Alignment(wrap_text=True, vertical="top")
        c2 = ws.cell(row=row, column=2, value=v)
        c2.alignment = Alignment(wrap_text=True, vertical="top")
        row += 1
    row += 1
    ws.cell(row=row, column=1, value="Per-respondent flag summary").font = Font(bold=True)
    row += 1
    _header_row(ws, row, ["Respondent", "Items", "Flagged"])
    row += 1
    for r in responses:
        response_items = get_response_items(r["id"])
        n_flagged = sum(1 for ri in response_items if ri["confidence"] != "ok")
        ws.cell(row=row, column=1, value=respondent_name(r)).border = BORDER
        ws.cell(row=row, column=2, value=len(response_items)).border = BORDER
        ws.cell(row=row, column=3, value=n_flagged).border = BORDER
        row += 1

    return wb


def export_batch_to_bytes(phase_id: int, phase_name: str, batch_id: int) -> bytes:
    wb = build_batch_workbook(phase_id, phase_name, batch_id)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
