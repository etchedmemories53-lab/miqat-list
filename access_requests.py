"""Firestore-backed access-request queue.

ALLOWED_EMAILS (auth.py) is a small, static "bootstrap admin" list read from
an env var - it exists so there's always at least one account that can sign
in and run Settings, even before this collection has anything in it. Every
other Google account that tries to sign in lands here instead: a pending row
an admin can approve or deny from the Settings UI, without touching env vars
or redeploying.
"""

from __future__ import annotations

from google.cloud import firestore

import db

ACCESS_REQUESTS = "access_requests"

PENDING = "pending"
APPROVED = "approved"
DENIED = "denied"


def _ref(email: str):
    return db.client().collection(ACCESS_REQUESTS).document(email)


def status_for(email: str) -> str | None:
    snap = _ref(email).get()
    return snap.to_dict().get("status") if snap.exists else None


def upsert_pending(email: str, name: str | None, picture: str | None) -> None:
    """Record a login attempt from a not-yet-approved account.

    Leaves an already-decided (approved/denied) row alone other than
    refreshing name/picture - re-attempting login is not how you get
    un-denied, an admin has to do that from Settings.
    """
    ref = _ref(email)
    snap = ref.get()
    if snap.exists:
        ref.update({"name": name, "picture": picture})
        return
    ref.set({
        "email": email,
        "name": name,
        "picture": picture,
        "status": PENDING,
        "requested_at": firestore.SERVER_TIMESTAMP,
    })


def _with_id(doc) -> dict:
    return {**doc.to_dict(), "id": doc.id}


def list_by_status(status: str) -> list[dict]:
    docs = db.client().collection(ACCESS_REQUESTS).where("status", "==", status).stream()
    rows = [_with_id(d) for d in docs]
    rows.sort(key=lambda r: r.get("requested_at") or 0, reverse=True)
    return rows


def count_pending() -> int:
    return sum(1 for _ in db.client().collection(ACCESS_REQUESTS).where("status", "==", PENDING).stream())


def approve(email: str) -> None:
    _ref(email).set({"status": APPROVED, "decided_at": firestore.SERVER_TIMESTAMP}, merge=True)


def deny(email: str) -> None:
    _ref(email).set({"status": DENIED, "decided_at": firestore.SERVER_TIMESTAMP}, merge=True)


def revoke(email: str) -> None:
    """Delete the row entirely - a revoked/removed user goes back to square one."""
    _ref(email).delete()
