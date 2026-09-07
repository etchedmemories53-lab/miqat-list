import csv
import io
import os
from datetime import date, datetime, timedelta

from flask import Flask, Response, jsonify, render_template, request

import cities
import miqaats
import sun
from hijri import HijriDate, days_in_month

app = Flask(__name__)

DEFAULT_PRIORITY = 1  # true miqats only, per the original app's sun/moon icon rule


def _parse_priority(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _hijri_payload(hijri: HijriDate) -> dict:
    return {
        "year": hijri.year,
        "month": hijri.month,
        "month_name": hijri.month_name,
        "day": hijri.day,
    }


def _day_payload(gregorian: date, priority: int | None, city: dict | None) -> dict:
    hijri = HijriDate.from_gregorian(gregorian)
    entries = miqaats.for_hijri_date(hijri, priority=priority)
    payload = {
        "gregorian_date": gregorian.isoformat(),
        "hijri_date": _hijri_payload(hijri),
        "miqaats": entries,
    }
    if city:
        payload["sun"] = sun.sun_times(city["latitude"], city["longitude"], city["timezone"], gregorian)
    return payload


def _year_payload(hijri_year: int, priority: int | None, city: dict | None) -> list[dict]:
    """One entry per Gregorian day within the given Hijri year that has matching miqaats."""
    day = HijriDate(hijri_year, 0, 1).to_gregorian()
    end = HijriDate(hijri_year, 11, days_in_month(hijri_year, 11)).to_gregorian()
    results = []
    while day <= end:
        hijri = HijriDate.from_gregorian(day)
        entries = miqaats.for_hijri_date(hijri, priority=priority)
        if entries:
            entry = {
                "gregorian_date": day.isoformat(),
                "day_name": day.strftime("%A"),
                "hijri_date": _hijri_payload(hijri),
                "miqaats": entries,
            }
            if city:
                entry["sun"] = sun.sun_times(city["latitude"], city["longitude"], city["timezone"], day)
            results.append(entry)
        day += timedelta(days=1)
    return results


def _resolve_city() -> dict | None:
    raw_city_id = request.args.get("city_id")
    if raw_city_id is None:
        return cities.get_city(cities.DEFAULT_CITY_ID)
    return cities.get_city(raw_city_id)


def _resolve_year_view_args() -> tuple[int, int | None, dict | None]:
    """(hijri_year, priority, city) from the current request's query params."""
    today_hijri_year = HijriDate.from_gregorian(date.today()).year
    hijri_year = request.args.get("year", type=int) or today_hijri_year

    raw_priority = request.args.get("priority")
    priority = DEFAULT_PRIORITY if raw_priority is None else _parse_priority(raw_priority)

    return hijri_year, priority, _resolve_city()


@app.get("/")
def index():
    today_iso = date.today().isoformat()
    hijri_year, priority, city = _resolve_year_view_args()

    entries = _year_payload(hijri_year, priority, city)
    past_entries = [e for e in entries if e["gregorian_date"] < today_iso]
    upcoming_entries = [e for e in entries if e["gregorian_date"] >= today_iso]

    return render_template(
        "index.html",
        hijri_year=hijri_year,
        priority=priority,
        past_entries=past_entries,
        upcoming_entries=upcoming_entries,
        today_iso=today_iso,
        city=city,
    )


@app.get("/download.csv")
def download_csv():
    hijri_year, priority, city = _resolve_year_view_args()
    entries = _year_payload(hijri_year, priority, city)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Gregorian Date", "Day", "Hijri Date", "Sunrise", "Sunset",
        "Miqaat", "Description", "Phase", "Priority",
    ])
    for entry in entries:
        hijri = entry["hijri_date"]
        hijri_str = f"{hijri['day']} {hijri['month_name']} {hijri['year']}H"
        sun_times = entry.get("sun") or {}
        for m in entry["miqaats"]:
            writer.writerow([
                entry["gregorian_date"], entry["day_name"], hijri_str,
                sun_times.get("sunrise") or "", sun_times.get("sunset") or "",
                m["title"], m["description"] or "", m["phase"], m["priority"],
            ])

    filename = f"miqat-list-{hijri_year}H.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/cities")
def api_cities():
    query = request.args.get("q", "")
    return jsonify(cities.search_cities(query))


@app.get("/api/miqats/today")
def api_today():
    priority = _parse_priority(request.args.get("priority"))
    city = _resolve_city() if "city_id" in request.args else None
    return jsonify(_day_payload(date.today(), priority, city))


@app.get("/api/miqats/year/<int:year>")
def api_by_year(year: int):
    priority = _parse_priority(request.args.get("priority"))
    city = _resolve_city() if "city_id" in request.args else None
    return jsonify(_year_payload(year, priority, city))


@app.get("/api/miqats/<iso_date>")
def api_by_date(iso_date: str):
    priority = _parse_priority(request.args.get("priority"))
    city = _resolve_city() if "city_id" in request.args else None
    try:
        gregorian = datetime.strptime(iso_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "date must be in YYYY-MM-DD format"}), 400
    return jsonify(_day_payload(gregorian, priority, city))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)
