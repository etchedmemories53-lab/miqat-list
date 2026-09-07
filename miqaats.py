"""Loading and filtering of the miqaat/urus dataset.

Data sourced from https://github.com/mygulamali/mumineen_calendar_js
(source/data/miqaats.json, MIT licensed) and matched by Hijri {month, date}
exactly as the original app's MiqaatList/CalendarDay components do:
an entry only counts once its optional `year` cutoff has been reached.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from hijri import HijriDate

DATA_PATH = Path(__file__).parent / "data" / "miqaats.json"

with DATA_PATH.open(encoding="utf-8") as f:
    _RAW = json.load(f)

# Index by (month, date) for O(1) lookup.
_BY_MONTH_DATE: dict[tuple[int, int], list[dict]] = {
    (entry["month"], entry["date"]): entry["miqaats"] for entry in _RAW
}


def for_hijri_date(hijri: HijriDate, priority: Optional[int] = None) -> list[dict]:
    """Miqaats/urus falling on the given Hijri date.

    priority=None returns everything; priority=N returns only entries with
    that exact priority (1 = true miqat, per the original app's icon logic).
    """
    entries = _BY_MONTH_DATE.get((hijri.month, hijri.day), [])
    result = []
    for entry in entries:
        if entry["year"] is not None and entry["year"] > hijri.year:
            continue
        if priority is not None and entry["priority"] != priority:
            continue
        result.append(entry)
    return result
