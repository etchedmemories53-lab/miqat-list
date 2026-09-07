"""Searchable city list backed by geonamescache (offline, no network calls).

Each city carries lat/lon and an IANA timezone name, which is exactly what
`sun.sun_times()` needs - no separate timezone-lookup step required.
"""

from __future__ import annotations

import geonamescache

_gc = geonamescache.GeonamesCache()
_CITIES = _gc.get_cities()  # geonameid (str) -> {name, latitude, longitude, countrycode, population, timezone, ...}

DEFAULT_CITY_ID = "4889447"  # Darien, IL - closest city in the dataset to Willowbrook, IL (~3km)


def _to_dict(city_id: str, c: dict) -> dict:
    return {
        "id": city_id,
        "name": c["name"],
        "country": c["countrycode"],
        "latitude": c["latitude"],
        "longitude": c["longitude"],
        "timezone": c["timezone"],
    }


def get_city(city_id: str | None) -> dict | None:
    if not city_id:
        return None
    c = _CITIES.get(city_id)
    return _to_dict(city_id, c) if c else None


def search_cities(query: str, limit: int = 10) -> list[dict]:
    query = query.strip().lower()
    if len(query) < 2:
        return []
    matches = [
        (c["population"], city_id, c)
        for city_id, c in _CITIES.items()
        if query in c["name"].lower()
    ]
    matches.sort(key=lambda t: -t[0])
    return [_to_dict(city_id, c) for _, city_id, c in matches[:limit]]
