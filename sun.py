"""Sunrise/sunset lookup via `astral` - pure computation, no network calls."""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from astral import LocationInfo
from astral.sun import sun as _astral_sun


def sun_times(latitude: float, longitude: float, timezone: str, on_date: date) -> dict:
    """Local sunrise/sunset (HH:MM) for a location on a given date.

    Returns None values for polar day/night, where the sun doesn't rise or
    set at all.
    """
    loc = LocationInfo(latitude=latitude, longitude=longitude, timezone=timezone)
    try:
        s = _astral_sun(loc.observer, date=on_date, tzinfo=ZoneInfo(timezone))
    except ValueError:
        return {"sunrise": None, "sunset": None}
    return {
        "sunrise": s["sunrise"].strftime("%H:%M"),
        "sunset": s["sunset"].strftime("%H:%M"),
    }
