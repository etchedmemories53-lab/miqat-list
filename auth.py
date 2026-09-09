"""Google sign-in for the whole app.

Cloud Run's own ingress stays --allow-unauthenticated (that's IAM-level
"can you reach the container at all" and only understands Google IAM
principals, not arbitrary Google accounts with an email allowlist) - this
module is the actual access gate, enforced by the app itself via a normal
OAuth login + session cookie, same on Cloud Run and locally.

Two tiers of access:
- Bootstrap admins: emails listed in the ALLOWED_EMAILS env var. Always let
  in, always able to reach Settings. This exists so there's always at least
  one account that can approve everyone else, even before Firestore has any
  access_requests rows.
- Everyone else: checked against the access_requests collection
  (access_requests.py). Not there yet, or still "pending"/"denied" -> shown
  a pending/denied page instead of the app, and (re-)recorded as pending so
  an admin can see and approve them from Settings.
"""

from __future__ import annotations

import os
from functools import wraps

from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.flask_client import OAuth
from flask import Blueprint, abort, redirect, render_template, request, session, url_for

import access_requests

oauth = OAuth()

bp = Blueprint("auth", __name__)


def init_app(app) -> None:
    oauth.init_app(app)
    oauth.register(
        name="google",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    app.register_blueprint(bp)


def bootstrap_admins() -> set[str]:
    raw = os.environ.get("ALLOWED_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


@bp.get("/login")
def login():
    redirect_uri = url_for("auth.callback", _external=True)
    next_url = request.args.get("next")
    if next_url:
        session["post_login_redirect"] = next_url
    return oauth.google.authorize_redirect(redirect_uri)


@bp.get("/auth/callback")
def callback():
    try:
        token = oauth.google.authorize_access_token()
    except OAuthError:
        # Stale/expired state (e.g. a reused or double-clicked login link) -
        # send them back through /login rather than a raw 500.
        session.clear()
        return redirect(url_for("auth.login"))

    user_info = token.get("userinfo") or {}
    email = (user_info.get("email") or "").lower()
    name = user_info.get("name") or email
    picture = user_info.get("picture")

    if not email:
        abort(403)

    is_admin = email in bootstrap_admins()
    if not is_admin:
        status = access_requests.status_for(email)
        if status != access_requests.APPROVED:
            access_requests.upsert_pending(email, name, picture)
            return render_template("pending.html", name=name, email=email, denied=(status == access_requests.DENIED))

    session["user"] = {"email": email, "name": name, "picture": picture, "is_admin": is_admin}
    next_url = session.pop("post_login_redirect", None)
    return redirect(next_url or url_for("index"))


@bp.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


def current_user() -> dict | None:
    return session.get("user")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("auth.login", next=request.url))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = session.get("user")
        if not user:
            return redirect(url_for("auth.login", next=request.url))
        if not user.get("is_admin"):
            abort(403)
        return view(*args, **kwargs)

    return wrapped
