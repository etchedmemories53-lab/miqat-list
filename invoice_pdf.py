"""Builds the Niyaz invoice PDF - a one-page summary of host details and the
cost breakdown for one miqaat occurrence. Uses reportlab (pure-Python, no
system packages needed) so the same bytes can be offered as a download and
attached to the email to the host.
"""

from __future__ import annotations

import io
import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from hijri import HijriDate
import niyaz
import org_info

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "static", "logo.png")


def _hijri_label(gregorian_date: str) -> str:
    hijri = HijriDate.from_gregorian(datetime.strptime(gregorian_date, "%Y-%m-%d").date())
    return f"{hijri.day} {hijri.month_name} {hijri.year}H"


def build(miqaat_title: str, gregorian_date: str, record: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.75 * inch)
    styles = getSampleStyleSheet()
    subtitle_style = ParagraphStyle("Subtitle", parent=styles["Heading3"], alignment=TA_CENTER, textColor=colors.HexColor("#6b6b6b"))
    party_heading = ParagraphStyle("PartyHeading", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9,
                                    textColor=colors.HexColor("#6b6b6b"), spaceAfter=5)
    party_heading_right = ParagraphStyle("PartyHeadingRight", parent=party_heading, alignment=TA_RIGHT)
    party_value = ParagraphStyle("PartyValue", parent=styles["Normal"], fontSize=9.5, leading=13)
    party_value_right = ParagraphStyle("PartyValueRight", parent=party_value, alignment=TA_RIGHT)

    story = []

    if os.path.exists(_LOGO_PATH):
        logo = Image(_LOGO_PATH, width=1.2 * inch, height=1.2 * inch)
        logo.hAlign = "CENTER"
        story.append(logo)
        story.append(Spacer(1, 0.1 * inch))

    story.append(Paragraph("Niyaz Invoice", styles["Title"]))
    story.append(Paragraph(miqaat_title, ParagraphStyle("MiqaatTitle", parent=styles["Heading3"], alignment=TA_CENTER)))
    story.append(Paragraph(f"{gregorian_date} &middot; {_hijri_label(gregorian_date)}", subtitle_style))
    story.append(Spacer(1, 0.3 * inch))

    host_column = [
        Paragraph("Host Details", party_heading),
        Paragraph(f"<b>Name:</b> {record.get('host_name', '')}", party_value),
        Paragraph(f"<b>ITS:</b> {record.get('host_its', '')}", party_value),
        Paragraph(f"<b>Email:</b> {record.get('host_email', '')}", party_value),
        Paragraph(f"<b>Phone:</b> {record.get('host_phone', '')}", party_value),
        Paragraph(f"<b>Number of Thals:</b> {record.get('thals', '')}", party_value),
    ]
    org_column = (
        [Paragraph(org_info.NAME, party_heading_right)]
        + [Paragraph(line, party_value_right) for line in org_info.ADDRESS_LINES]
    )

    info_table = Table([[host_column, org_column]], colWidths=[3.3 * inch, 3.3 * inch])
    info_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(info_table)
    story.append(Spacer(1, 0.3 * inch))

    line_items = record.get("line_items") or []
    total = niyaz.total_cost(line_items)
    per_thal = niyaz.cost_per_thal(line_items, record.get("thals"))

    item_rows = [["Item", "Amount"]]
    item_rows += [[item.get("label", ""), f"${item.get('amount') or 0:.2f}"] for item in line_items]
    item_rows.append(["Total", f"${total:.2f}"])
    item_rows.append(["Cost per Thal", f"${per_thal:.2f}" if per_thal is not None else "—"])

    items_table = Table(item_rows, colWidths=[4.6 * inch, 2.0 * inch])
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#b5651d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -2), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -2), (-1, -2), 1, colors.black),
        ("GRID", (0, 0), (-1, -3), 0.5, colors.HexColor("#e0ddd6")),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(items_table)

    doc.build(story)
    return buffer.getvalue()
