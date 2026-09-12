"""One-time personal functions (Shadi, Misaq, Shitabi, Majalis, Soyem, or a
custom type) added by a user for a specific date.

Unlike miqaats, these never recur - each row is a single occasion, so it's
looked up by its exact Gregorian date instead of a recurring Hijri
month/day rule. The Hijri equivalent is stored alongside it purely so the
main table (which is organized by Hijri date) can display it.
"""

from __future__ import annotations

from datetime import date

import db
from hijri import HijriDate

TYPE_LABELS = {
    "shadi": "Shadi",
    "misaq": "Misaq",
    "shitabi": "Shitabi",
    "majalis": "Majalis",
    "soyem": "Soyem",
    "other": "Other",
}

TYPES = list(TYPE_LABELS)


def _entry_dict(doc) -> dict:
    data = doc.to_dict()
    type_ = data["type"]
    title = data.get("custom_type") if type_ == "other" and data.get("custom_type") else TYPE_LABELS.get(type_, type_)
    return {
        "id": doc.id,
        "kind": "personal",
        "title": title,
        "description": data.get("details"),
        "phase": None,
        "priority_id": None,
        "type": type_,
    }


def create(type_: str, custom_type: str | None, details: str | None, gregorian_date: date) -> str:
    if type_ not in TYPE_LABELS:
        raise ValueError(f"unknown personal function type {type_!r}")

    hijri = HijriDate.from_gregorian(gregorian_date)
    data = {
        "type": type_,
        "custom_type": custom_type if type_ == "other" else None,
        "details": details,
        "gregorian_date": gregorian_date.isoformat(),
        "hijri_year": hijri.year,
        "hijri_month": hijri.month,
        "hijri_day": hijri.day,
    }
    ref = db.client().collection(db.PERSONAL_FUNCTIONS).document()
    ref.set(data)
    return ref.id


def load_for_range(start_iso: str, end_iso: str) -> dict[str, list[dict]]:
    """gregorian_date (iso) -> matching entries, for dates within [start, end]."""
    query = (
        db.client().collection(db.PERSONAL_FUNCTIONS)
        .where("gregorian_date", ">=", start_iso)
        .where("gregorian_date", "<=", end_iso)
    )
    index: dict[str, list[dict]] = {}
    for doc in query.stream():
        entry = _entry_dict(doc)
        index.setdefault(doc.to_dict()["gregorian_date"], []).append(entry)
    return index


def for_date(iso_date: str) -> list[dict]:
    return load_for_range(iso_date, iso_date).get(iso_date, [])


def remove(function_id: str) -> None:
    ref = db.client().collection(db.PERSONAL_FUNCTIONS).document(function_id)
    if not ref.get().exists:
        raise ValueError(f"personal function {function_id!r} does not exist")
    ref.delete()
