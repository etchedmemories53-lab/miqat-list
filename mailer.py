"""Sends the Niyaz invoice details to a host by email - the full breakdown
is written directly into the email body (HTML with a plain-text fallback)
rather than attached as a PDF, so a host can read it without downloading
anything. Uses whatever SMTP account is configured under Settings > Email
(SMTP); nothing is baked in, so sending raises NotConfigured until that's
filled in.
"""

from __future__ import annotations

import os
import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import invoice_email
import smtp_settings

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "static", "logo.png")


class NotConfigured(Exception):
    pass


def send_invoice(to_email: str, miqaat_title: str, gregorian_date: str, hijri_date: str, record: dict) -> None:
    if not smtp_settings.is_configured():
        raise NotConfigured("SMTP is not configured yet - add it under Settings > Email (SMTP).")
    config = smtp_settings.get()
    has_logo = os.path.exists(_LOGO_PATH)

    msg = MIMEMultipart("related")
    msg["Subject"] = f"Niyaz Invoice - {miqaat_title} ({gregorian_date})"
    msg["From"] = f"{config.get('from_name', '')} <{config['from_email']}>".strip()
    msg["To"] = to_email

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(invoice_email.render_text(miqaat_title, gregorian_date, hijri_date, record), "plain"))
    alt.attach(MIMEText(invoice_email.render_html(miqaat_title, gregorian_date, hijri_date, record, has_logo), "html"))
    msg.attach(alt)

    if has_logo:
        with open(_LOGO_PATH, "rb") as f:
            logo = MIMEImage(f.read())
        logo.add_header("Content-ID", f"<{invoice_email.LOGO_CID}>")
        logo.add_header("Content-Disposition", "inline", filename="logo.png")
        msg.attach(logo)

    with smtplib.SMTP(config["host"], int(config.get("port") or 587), timeout=15) as server:
        if config.get("use_tls", True):
            server.starttls()
        if config.get("username"):
            server.login(config["username"], config.get("password", ""))
        server.sendmail(config["from_email"], [to_email], msg.as_string())
