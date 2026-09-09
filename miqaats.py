"""Firestore-backed miqaat/urus queries.

Data model:
  priorities/{id}   -> {"name": str}
  miqaats/{id}      -> {
      "title": str, "description": str | None, "phase": "day" | "night",
      "year": int | None,
      "priority_id": str,   # "foreign key" into priorities/{id}
      "recurrence_type": "hijri" | "weekly",   # missing on old rows == "hijri"
      # recurrence_type == "hijri":
      "hijri_month": int, "hijri_day": int,
      # recurrence_type == "weekly":
      "weekday": int,   # 0 = Monday .. 6 = Sunday, same as date.weekday()
  }

Originally sourced from https://github.com/mygulamali/mumineen_calendar_js
(source/data/miqaats.json, MIT licensed) - that file is now only the seed
data (see scripts/seed_firestore.py), not something the app reads directly.
Every row seeded from there is "hijri" recurrence; "weekly" rows are only
ever user-added, straight into the HOSTED_PRIORITY_ID bucket.
"""

from __future__ import annotations

from typing import Optional

import db
from hijri import HijriDate

HOSTED_PRIORITY_ID = "4"

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _entry_dict(doc) -> dict:
    data = doc.to_dict()
    recurrence_type = data.get("recurrence_type", "hijri")
    weekday = data.get("weekday")
    return {
        "id": doc.id,
        "title": data["title"],
        "description": data.get("description"),
        "phase": data["phase"],
        "year": data.get("year"),
        "priority_id": data["priority_id"],
        "recurrence_type": recurrence_type,
        "weekday": weekday,
        "recurrence_label": f"every {WEEKDAY_NAMES[weekday]}" if recurrence_type == "weekly" and weekday is not None else None,
    }


def for_hijri_date(hijri: HijriDate, priority: Optional[str] = None) -> list[dict]:
    """Miqaats/urus falling on the given Hijri date.

    priority=None returns every priority; priority="1".."4" filters to that
    exact priority_id.
    """
    query = (
        db.client().collection(db.MIQAATS)
        .where("hijri_month", "==", hijri.month)
        .where("hijri_day", "==", hijri.day)
    )
    if priority is not None:
        query = query.where("priority_id", "==", priority)

    result = []
    for doc in query.stream():
        entry = _entry_dict(doc)
        if entry["year"] is not None and entry["year"] > hijri.year:
            continue
        result.append(entry)
    return result


def load_year_index(hijri_year: int, priority: Optional[str] = None) -> dict[tuple[int, int], list[dict]]:
    """(hijri_month, hijri_day) -> matching entries, for the whole Hijri year.

    One Firestore read for the whole year's view instead of one per day -
    every date in a single Hijri year shares the same year-cutoff check.
    """
    query = db.client().collection(db.MIQAATS)
    if priority is not None:
        query = query.where("priority_id", "==", priority)

    index: dict[tuple[int, int], list[dict]] = {}
    for doc in query.stream():
        data = doc.to_dict()
        if data.get("recurrence_type", "hijri") != "hijri":
            continue  # weekly-recurring rows live in load_weekly_index instead
        if data.get("year") is not None and data["year"] > hijri_year:
            continue
        key = (data["hijri_month"], data["hijri_day"])
        index.setdefault(key, []).append(_entry_dict(doc))
    return index


def for_weekday(weekday: int, priority: Optional[str] = None) -> list[dict]:
    """Weekly-recurring miqaats/majalis that fall on the given weekday (0=Monday..6=Sunday)."""
    query = (
        db.client().collection(db.MIQAATS)
        .where("recurrence_type", "==", "weekly")
        .where("weekday", "==", weekday)
    )
    if priority is not None:
        query = query.where("priority_id", "==", priority)
    return [_entry_dict(doc) for doc in query.stream()]


def load_weekly_index(priority: Optional[str] = None) -> dict[int, list[dict]]:
    """weekday (0=Monday..6=Sunday) -> matching weekly-recurring entries.

    One Firestore read for every weekly entry, mirroring load_year_index -
    the same handful of rows apply to every week of the year being rendered.
    """
    query = db.client().collection(db.MIQAATS).where("recurrence_type", "==", "weekly")
    if priority is not None:
        query = query.where("priority_id", "==", priority)

    index: dict[int, list[dict]] = {}
    for doc in query.stream():
        entry = _entry_dict(doc)
        index.setdefault(entry["weekday"], []).append(entry)
    return index


def create_hosted(
    title: str,
    description: Optional[str],
    phase: str,
    recurrence_type: str,
    hijri_month: Optional[int] = None,
    hijri_day: Optional[int] = None,
    weekday: Optional[int] = None,
) -> str:
    """User-authored addition, straight into the "ASChicago Hosted" priority.

    Unlike copy_to_hosted, this has no source miqaat - it's a brand new row,
    so there's no "copied_from" and it never shows up in copied_source_ids().
    """
    db.require_priority(HOSTED_PRIORITY_ID)

    data = {
        "title": title,
        "description": description,
        "phase": phase,
        "year": None,
        "priority_id": HOSTED_PRIORITY_ID,
        "recurrence_type": recurrence_type,
    }
    if recurrence_type == "hijri":
        data["hijri_month"] = hijri_month
        data["hijri_day"] = hijri_day
    elif recurrence_type == "weekly":
        data["weekday"] = weekday
    else:
        raise ValueError(f"unknown recurrence_type {recurrence_type!r}")

    ref = db.client().collection(db.MIQAATS).document()
    ref.set(data)
    return ref.id


def copied_source_ids() -> set[str]:
    """ids of every miqaat that already has a copy in the hosted priority."""
    query = db.client().collection(db.MIQAATS).where("priority_id", "==", HOSTED_PRIORITY_ID)
    ids = set()
    for doc in query.stream():
        source_id = doc.to_dict().get("copied_from")
        if source_id:
            ids.add(source_id)
    return ids


def copy_to_hosted(miqaat_id: str) -> str:
    """Copy an existing miqaat into the "ASChicago Hosted" priority.

    Idempotent: if this miqaat was already copied, returns the existing
    copy's id instead of creating a second one. Returns the document's id.
    Raises db.ForeignKeyError if the hosted priority somehow doesn't exist,
    or ValueError if the source doesn't.
    """
    db.require_priority(HOSTED_PRIORITY_ID)

    existing = (
        db.client().collection(db.MIQAATS)
        .where("priority_id", "==", HOSTED_PRIORITY_ID)
        .where("copied_from", "==", miqaat_id)
        .limit(1)
        .get()
    )
    if existing:
        return existing[0].id

    source = db.client().collection(db.MIQAATS).document(miqaat_id).get()
    if not source.exists:
        raise ValueError(f"miqaat {miqaat_id!r} does not exist")

    data = source.to_dict()
    data["priority_id"] = HOSTED_PRIORITY_ID
    data["copied_from"] = miqaat_id

    new_ref = db.client().collection(db.MIQAATS).document()
    new_ref.set(data)
    return new_ref.id


def remove_hosted(miqaat_id: str) -> None:
    """Delete a hosted ("ASChicago Hosted") miqaat.

    Refuses to delete anything whose priority_id isn't HOSTED_PRIORITY_ID,
    so this can't be repurposed to wipe seeded data.
    """
    ref = db.client().collection(db.MIQAATS).document(miqaat_id)
    snap = ref.get()
    if not snap.exists:
        raise ValueError(f"miqaat {miqaat_id!r} does not exist")
    if snap.to_dict().get("priority_id") != HOSTED_PRIORITY_ID:
        raise ValueError(f"miqaat {miqaat_id!r} is not a hosted entry - refusing to remove")
    ref.delete()
