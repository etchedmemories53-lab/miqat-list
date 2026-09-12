"""Cost/logistics breakdown for a hosted miqaat's Niyaz (food) on one
specific date - kept separate from the miqaat's own recurring definition,
since thal counts and grocery costs change every time it's actually served
(e.g. "Milad Imam uz-Zaman" recurs every year, but each year gets its own
Niyaz record, keyed by that year's Gregorian date).

Data model:
  niyaz/{miqaat_id}__{gregorian_date} -> {
      "miqaat_id": str, "gregorian_date": "YYYY-MM-DD",
      "thals": int,
      "host_name": str, "host_its": str, "host_email": str, "host_phone": str,
      "line_items": [{"label": str, "amount": float}, ...],
      "menu_items": [{"label": str, "details": str}, ...],
  }
"""

from __future__ import annotations

import re
import secrets

from werkzeug.security import check_password_hash, generate_password_hash

import db

DEFAULT_LINE_ITEMS = ["Grocery - Rice", "Grocery - Meat", "Mawaid Cost", "Cleaning", "Jamaat Laagat"]

DEFAULT_MENU_ITEMS = [
    "Namak", "Kharas 1", "Roti", "Tarkari", "Rice",
    "Gravy/Soup/Matho", "Salad", "Fruits", "Mithas", "Sharbat",
]

_DEFAULTS_COLLECTION = "app_settings"
_DEFAULTS_DOC_ID = "niyaz_line_items"

ITS_RE = re.compile(r"^\d{8}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[0-9 ()-]{7,20}$")


def _doc_id(miqaat_id: str, gregorian_date: str) -> str:
    return f"{miqaat_id}__{gregorian_date}"


def get(miqaat_id: str, gregorian_date: str) -> dict | None:
    snap = db.client().collection(db.NIYAZ).document(_doc_id(miqaat_id, gregorian_date)).get()
    return snap.to_dict() if snap.exists else None


def summary_index() -> dict[str, dict]:
    """"{miqaat_id}__{gregorian_date}" -> {"host_name", "total_cost"} for every
    saved Niyaz record - lets the table show host/cost and "Edit" vs "Add"
    without a per-row Firestore read."""
    index = {}
    for doc in db.client().collection(db.NIYAZ).stream():
        data = doc.to_dict()
        index[doc.id] = {
            "host_name": data.get("host_name", ""),
            "total_cost": total_cost(data.get("line_items") or []),
        }
    return index


def validate(host_name: str, host_its: str, host_email: str, host_phone: str, thals: int | None, line_items: list[dict]) -> list[str]:
    errors = []
    if not host_name:
        errors.append("Host name is required.")
    if not ITS_RE.match(host_its or ""):
        errors.append("Host ITS must be exactly 8 digits.")
    if not EMAIL_RE.match(host_email or ""):
        errors.append("Enter a valid host email address.")
    if not PHONE_RE.match(host_phone or ""):
        errors.append("Enter a valid host phone number.")
    if thals is None or thals < 1:
        errors.append("Number of thals must be at least 1.")
    if not line_items:
        errors.append("Add at least one cost line item.")
    return errors


def save(
    miqaat_id: str,
    gregorian_date: str,
    *,
    thals: int,
    host_name: str,
    host_its: str,
    host_email: str,
    host_phone: str,
    line_items: list[dict],
) -> None:
    """Saves the Finance half of the record - merges rather than replaces,
    so it never wipes out a menu already saved independently via save_menu()."""
    data = {
        "miqaat_id": miqaat_id,
        "gregorian_date": gregorian_date,
        "thals": thals,
        "host_name": host_name,
        "host_its": host_its,
        "host_email": host_email,
        "host_phone": host_phone,
        "line_items": line_items,
    }
    db.client().collection(db.NIYAZ).document(_doc_id(miqaat_id, gregorian_date)).set(data, merge=True)


def save_menu(miqaat_id: str, gregorian_date: str, menu_items: list[dict]) -> None:
    """Saves the Menu half of the record - merges rather than replaces, so
    it never wipes out Finance details saved independently via save()."""
    data = {
        "miqaat_id": miqaat_id,
        "gregorian_date": gregorian_date,
        "menu_items": menu_items,
    }
    db.client().collection(db.NIYAZ).document(_doc_id(miqaat_id, gregorian_date)).set(data, merge=True)


def total_cost(line_items: list[dict]) -> float:
    return sum(item.get("amount") or 0 for item in line_items)


def cost_per_thal(line_items: list[dict], thals: int | None) -> float | None:
    if not thals:
        return None
    return total_cost(line_items) / thals


def create_share(miqaat_id: str, gregorian_date: str) -> tuple[str, str]:
    """(token, plaintext_password) for a new password-protected, no-Google-login
    invoice link - regenerating replaces any previous token/password, so an
    old link stops working the moment a new one is issued. The plaintext
    password is returned once and never stored - only its hash is."""
    token = secrets.token_urlsafe(24)
    password = secrets.token_urlsafe(9)
    db.client().collection(db.NIYAZ).document(_doc_id(miqaat_id, gregorian_date)).update({
        "share_token": token,
        "share_password_hash": generate_password_hash(password),
    })
    return token, password


def get_by_token(token: str) -> dict | None:
    docs = db.client().collection(db.NIYAZ).where("share_token", "==", token).limit(1).get()
    return docs[0].to_dict() if docs else None


def verify_share_password(record: dict, password: str) -> bool:
    password_hash = record.get("share_password_hash")
    return bool(password_hash) and check_password_hash(password_hash, password)


def delete(miqaat_id: str, gregorian_date: str) -> None:
    db.client().collection(db.NIYAZ).document(_doc_id(miqaat_id, gregorian_date)).delete()


def get_default_line_item_labels() -> list[str]:
    """Admin-configurable starting checklist for a new Niyaz form (Settings >
    Niyaz Default Items) - falls back to the built-in seed list until an
    admin saves their own."""
    snap = db.client().collection(_DEFAULTS_COLLECTION).document(_DEFAULTS_DOC_ID).get()
    if snap.exists:
        items = snap.to_dict().get("items")
        if items:
            return items
    return list(DEFAULT_LINE_ITEMS)


def save_default_line_item_labels(labels: list[str]) -> None:
    db.client().collection(_DEFAULTS_COLLECTION).document(_DEFAULTS_DOC_ID).set({"items": labels})
