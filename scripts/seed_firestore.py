"""One-off, idempotent import: data/miqaats.json -> Firestore.

Run against the local emulator (docker-compose sets FIRESTORE_EMULATOR_HOST)
or, with real GCP credentials, against a deployed project. Deterministic
document ids make re-running safe - it overwrites the same documents rather
than duplicating them.

Usage: python scripts/seed_firestore.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import db  # noqa: E402

DATA_PATH = Path(__file__).parent.parent / "data" / "miqaats.json"

PRIORITY_NAMES = {
    "1": "Miqat",
    "2": "Priority 2",
    "3": "Priority 3",
    "4": "ASChicago Hosted",
}

BATCH_LIMIT = 400  # Firestore caps a batch at 500 writes


def seed_priorities() -> None:
    for priority_id, name in PRIORITY_NAMES.items():
        db.client().collection(db.PRIORITIES).document(priority_id).set({"name": name})
    print(f"Seeded {len(PRIORITY_NAMES)} priorities.")


def seed_miqaats() -> None:
    with DATA_PATH.open(encoding="utf-8") as f:
        raw = json.load(f)

    batch = db.client().batch()
    pending = 0
    total = 0
    for day_entry in raw:
        month, date_ = day_entry["month"], day_entry["date"]
        for i, m in enumerate(day_entry["miqaats"]):
            priority_id = str(m["priority"])
            if priority_id not in PRIORITY_NAMES:
                raise db.ForeignKeyError(
                    f"miqaats.json has priority {priority_id!r} at month={month} "
                    f"date={date_}, which isn't one of {sorted(PRIORITY_NAMES)}"
                )
            doc_id = f"{month:02d}-{date_:02d}-{i}"
            ref = db.client().collection(db.MIQAATS).document(doc_id)
            batch.set(ref, {
                "hijri_month": month,
                "hijri_day": date_,
                "title": m["title"],
                "description": m["description"],
                "phase": m["phase"],
                "year": m["year"],
                "priority_id": priority_id,
            })
            total += 1
            pending += 1
            if pending >= BATCH_LIMIT:
                batch.commit()
                batch = db.client().batch()
                pending = 0
    if pending:
        batch.commit()
    print(f"Seeded {total} miqaat documents.")


if __name__ == "__main__":
    seed_priorities()
    seed_miqaats()
