"""SMTP configuration for outbound email (Niyaz invoices to hosts).

Stored in Firestore so it can be filled in from Settings without a
redeploy - there's exactly one row, since this app only ever sends mail
through one outbound account. The password is kept in plaintext here (not
hashed) because the app needs to present it back to the SMTP server on
every send; there's no separate secret store in this project to defer to.
"""

from __future__ import annotations

import db

_COLLECTION = "app_settings"
_DOC_ID = "smtp"


def _ref():
    return db.client().collection(_COLLECTION).document(_DOC_ID)


def get() -> dict:
    snap = _ref().get()
    return snap.to_dict() if snap.exists else {}


def is_configured() -> bool:
    config = get()
    return bool(config.get("host") and config.get("from_email"))


def save(*, host: str, port: int, username: str, password: str, from_email: str, from_name: str, use_tls: bool) -> None:
    _ref().set({
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "from_email": from_email,
        "from_name": from_name,
        "use_tls": use_tls,
    })
