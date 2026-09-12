"""Settings: bootstrap-admin-only pages, registered in every environment
(unlike admin.py's raw DB browser, which only exists locally).
"""

from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, url_for

import access_requests
import auth
import niyaz
import smtp_settings

bp = Blueprint("settings", __name__, url_prefix="/settings")


def _format_timestamp(row: dict) -> str:
    ts = row.get("decided_at") or row.get("requested_at")
    return ts.strftime("%Y-%m-%d %H:%M") if ts else ""


@bp.get("/")
@auth.admin_required
def index():
    return render_template("settings.html", pending_count=access_requests.count_pending())


@bp.get("/access")
@auth.admin_required
def access_requests_page():
    pending = access_requests.list_by_status(access_requests.PENDING)
    approved = access_requests.list_by_status(access_requests.APPROVED)
    denied = access_requests.list_by_status(access_requests.DENIED)
    for row in pending + approved + denied:
        row["timestamp_label"] = _format_timestamp(row)
    return render_template("settings_access.html", pending=pending, approved=approved, denied=denied)


@bp.post("/access/<email>/approve")
@auth.admin_required
def approve(email: str):
    access_requests.approve(email)
    return redirect(url_for("settings.access_requests_page"))


@bp.post("/access/<email>/deny")
@auth.admin_required
def deny(email: str):
    access_requests.deny(email)
    return redirect(url_for("settings.access_requests_page"))


@bp.post("/access/<email>/revoke")
@auth.admin_required
def revoke(email: str):
    access_requests.revoke(email)
    return redirect(url_for("settings.access_requests_page"))


@bp.post("/access/<email>/promote")
@auth.admin_required
def promote(email: str):
    access_requests.promote_to_admin(email)
    return redirect(url_for("settings.access_requests_page"))


@bp.post("/access/<email>/demote")
@auth.admin_required
def demote(email: str):
    access_requests.demote_from_admin(email)
    return redirect(url_for("settings.access_requests_page"))


@bp.get("/smtp")
@auth.admin_required
def smtp_page():
    return render_template("settings_smtp.html", config=smtp_settings.get(), error=None)


@bp.post("/smtp")
@auth.admin_required
def save_smtp():
    form = request.form
    existing = smtp_settings.get()

    host = form.get("host", "").strip()
    port = form.get("port", type=int)
    username = form.get("username", "").strip()
    password = form.get("password", "") or existing.get("password", "")
    from_email = form.get("from_email", "").strip()
    from_name = form.get("from_name", "").strip()
    use_tls = form.get("use_tls") == "on"

    errors = []
    if not host:
        errors.append("SMTP host is required.")
    if not port:
        errors.append("Port is required.")
    if not from_email:
        errors.append("From email is required.")

    if errors:
        return render_template(
            "settings_smtp.html",
            config={
                "host": host, "port": port, "username": username, "password": password,
                "from_email": from_email, "from_name": from_name, "use_tls": use_tls,
            },
            error=" ".join(errors),
        ), 400

    smtp_settings.save(
        host=host, port=port, username=username, password=password,
        from_email=from_email, from_name=from_name, use_tls=use_tls,
    )
    return redirect(url_for("settings.smtp_page"))


@bp.get("/niyaz-items")
@auth.admin_required
def niyaz_items_page():
    return render_template("settings_niyaz_items.html", items=niyaz.get_default_line_item_labels(), error=None)


@bp.post("/niyaz-items")
@auth.admin_required
def save_niyaz_items():
    labels = [label.strip() for label in request.form.getlist("item_label") if label.strip()]
    if not labels:
        return render_template("settings_niyaz_items.html", items=[""], error="Add at least one default item."), 400

    niyaz.save_default_line_item_labels(labels)
    return redirect(url_for("index"))
