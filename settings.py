"""Settings: bootstrap-admin-only pages, registered in every environment
(unlike admin.py's raw DB browser, which only exists locally).
"""

from __future__ import annotations

from flask import Blueprint, redirect, render_template, url_for

import access_requests
import auth

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
