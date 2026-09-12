"""Renders the Niyaz invoice as an email body (HTML + plain-text fallback)
instead of a PDF attachment, so a host can read the full breakdown right in
their inbox. Mirrors the layout of the on-screen/PDF invoice: logo up top,
host details and organization details side by side, then the cost table.
"""

from __future__ import annotations

import niyaz
import org_info

LOGO_CID = "invoice-logo"


def render_html(miqaat_title: str, gregorian_date: str, hijri_date: str, record: dict, has_logo: bool) -> str:
    line_items = record.get("line_items") or []
    total = niyaz.total_cost(line_items)
    per_thal = niyaz.cost_per_thal(line_items, record.get("thals"))

    rows = "".join(
        f'<tr><td style="padding:6px 8px;border-bottom:1px solid #e0ddd6;">{item.get("label", "")}</td>'
        f'<td style="padding:6px 8px;text-align:right;border-bottom:1px solid #e0ddd6;">${item.get("amount") or 0:.2f}</td></tr>'
        for item in line_items
    )
    logo_html = (
        f'<img src="cid:{LOGO_CID}" alt="{org_info.NAME}" style="max-width:110px;height:auto;">'
        if has_logo else ""
    )
    address_html = "".join(f'<p style="margin:2px 0;">{line}</p>' for line in org_info.ADDRESS_LINES)
    per_thal_label = f"${per_thal:.2f}" if per_thal is not None else "&mdash;"

    return f"""\
<div style="font-family:Arial,Helvetica,sans-serif;max-width:480px;margin:0 auto;color:#1a1a1a;">
  <div style="text-align:center;margin-bottom:20px;">
    {logo_html}
    <h2 style="margin:12px 0 0;font-size:20px;">Niyaz Invoice</h2>
    <p style="margin:6px 0 0;font-weight:600;">{miqaat_title}</p>
    <p style="margin:2px 0 0;color:#6b6b6b;font-size:13px;">{gregorian_date} &middot; {hijri_date}</p>
  </div>
  <table width="100%" style="margin-bottom:18px;border-collapse:collapse;">
    <tr>
      <td style="vertical-align:top;width:50%;">
        <p style="font-size:11px;text-transform:uppercase;color:#6b6b6b;margin:0 0 6px;letter-spacing:0.03em;">Host Details</p>
        <p style="margin:2px 0;font-size:13px;"><b>Name:</b> {record.get('host_name', '')}</p>
        <p style="margin:2px 0;font-size:13px;"><b>ITS:</b> {record.get('host_its', '')}</p>
        <p style="margin:2px 0;font-size:13px;"><b>Email:</b> {record.get('host_email', '')}</p>
        <p style="margin:2px 0;font-size:13px;"><b>Phone:</b> {record.get('host_phone', '')}</p>
        <p style="margin:2px 0;font-size:13px;"><b>Number of Thals:</b> {record.get('thals', '')}</p>
      </td>
      <td style="vertical-align:top;width:50%;text-align:right;">
        <p style="font-size:11px;text-transform:uppercase;color:#6b6b6b;margin:0 0 6px;letter-spacing:0.03em;">{org_info.NAME}</p>
        {address_html}
      </td>
    </tr>
  </table>
  <table width="100%" cellspacing="0" style="border-collapse:collapse;">
    <tr style="background:#b5651d;color:#ffffff;">
      <th style="text-align:left;padding:8px;font-size:13px;">Item</th>
      <th style="text-align:right;padding:8px;font-size:13px;">Amount</th>
    </tr>
    {rows}
    <tr>
      <td style="padding:8px;font-weight:bold;border-top:1px solid #1a1a1a;">Total</td>
      <td style="padding:8px;text-align:right;font-weight:bold;border-top:1px solid #1a1a1a;">${total:.2f}</td>
    </tr>
    <tr>
      <td style="padding:8px;font-weight:bold;">Cost per Thal</td>
      <td style="padding:8px;text-align:right;font-weight:bold;">{per_thal_label}</td>
    </tr>
  </table>
</div>
"""


def render_text(miqaat_title: str, gregorian_date: str, hijri_date: str, record: dict) -> str:
    line_items = record.get("line_items") or []
    total = niyaz.total_cost(line_items)
    per_thal = niyaz.cost_per_thal(line_items, record.get("thals"))

    lines = [
        "Niyaz Invoice",
        f"{miqaat_title} - {gregorian_date} ({hijri_date})",
        "",
        "Host Details",
        f"Name: {record.get('host_name', '')}",
        f"ITS: {record.get('host_its', '')}",
        f"Email: {record.get('host_email', '')}",
        f"Phone: {record.get('host_phone', '')}",
        f"Number of Thals: {record.get('thals', '')}",
        "",
        org_info.NAME,
        *org_info.ADDRESS_LINES,
        "",
        "Cost Breakdown",
    ]
    lines += [f"  {item.get('label', '')}: ${item.get('amount') or 0:.2f}" for item in line_items]
    lines.append(f"Total: ${total:.2f}")
    lines.append(f"Cost per Thal: {'$%.2f' % per_thal if per_thal is not None else '-'}")
    return "\n".join(lines)
