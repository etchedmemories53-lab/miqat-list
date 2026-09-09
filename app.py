import csv
import io
import os
from datetime import date, datetime, timedelta

from flask import Flask, Response, jsonify, redirect, render_template, request, url_for

import access_requests
import auth
import cities
import db
import miqaats
import settings
import sun
from hijri import MONTH_NAMES, HijriDate, days_in_month

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]
auth.init_app(app)
app.register_blueprint(settings.bp)

# Only present locally (docker-compose sets it); never set on Cloud Run, where
# auth goes through the attached service account instead. Gating the admin
# blueprint's registration on it means those routes don't exist at all in
# production, regardless of what code gets deployed.
ADMIN_ENABLED = bool(os.environ.get("FIRESTORE_EMULATOR_HOST"))
if ADMIN_ENABLED:
    import admin
    app.register_blueprint(admin.bp)

DEFAULT_PRIORITY = "1"  # true miqats only, per the original app's sun/moon icon rule


@app.context_processor
def inject_globals():
    user = auth.current_user()
    return {
        "current_user": user,
        "admin_enabled": ADMIN_ENABLED,
        "pending_count": access_requests.count_pending() if user and user.get("is_admin") else None,
    }


@app.errorhandler(403)
def forbidden(_exc):
    return "You don't have permission to view this page.", 403


def _parse_priority(raw: str | None) -> str | None:
    return raw or None


def _hijri_payload(hijri: HijriDate) -> dict:
    return {
        "year": hijri.year,
        "month": hijri.month,
        "month_name": hijri.month_name,
        "month_name_short": hijri.month_name_short,
        "day": hijri.day,
    }


def _day_payload(gregorian: date, priority: str | None, city: dict | None) -> dict:
    hijri = HijriDate.from_gregorian(gregorian)
    entries = miqaats.for_hijri_date(hijri, priority=priority) + miqaats.for_weekday(gregorian.weekday(), priority=priority)
    payload = {
        "gregorian_date": gregorian.isoformat(),
        "hijri_date": _hijri_payload(hijri),
        "miqaats": entries,
    }
    if city:
        payload["sun"] = sun.sun_times(city["latitude"], city["longitude"], city["timezone"], gregorian)
    return payload


def _year_payload(hijri_year: int, priority: str | None, city: dict | None) -> list[dict]:
    """One entry per Gregorian day within the given Hijri year that has matching miqaats."""
    index = miqaats.load_year_index(hijri_year, priority=priority)
    weekly_index = miqaats.load_weekly_index(priority=priority)
    day = HijriDate(hijri_year, 0, 1).to_gregorian()
    end = HijriDate(hijri_year, 11, days_in_month(hijri_year, 11)).to_gregorian()
    results = []
    while day <= end:
        hijri = HijriDate.from_gregorian(day)
        entries = index.get((hijri.month, hijri.day), []) + weekly_index.get(day.weekday(), [])
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


def _resolve_year_view_args() -> tuple[int, str | None, dict | None]:
    """(hijri_year, priority, city) from the current request's query params."""
    today_hijri_year = HijriDate.from_gregorian(date.today()).year
    hijri_year = request.args.get("year", type=int) or today_hijri_year

    raw_priority = request.args.get("priority")
    priority = DEFAULT_PRIORITY if raw_priority is None else _parse_priority(raw_priority)

    return hijri_year, priority, _resolve_city()


@app.get("/")
@auth.login_required
def index():
    today_iso = date.today().isoformat()
    hijri_year, priority, city = _resolve_year_view_args()

    entries = _year_payload(hijri_year, priority, city)
    past_entries = [e for e in entries if e["gregorian_date"] < today_iso]
    upcoming_entries = [e for e in entries if e["gregorian_date"] >= today_iso]

    priority_names = {pid: p["name"] for pid, p in db.all_priorities().items()}
    copied_ids = miqaats.copied_source_ids()

    return render_template(
        "index.html",
        hijri_year=hijri_year,
        priority=priority,
        past_entries=past_entries,
        upcoming_entries=upcoming_entries,
        today_iso=today_iso,
        city=city,
        priority_names=priority_names,
        hosted_priority_id=miqaats.HOSTED_PRIORITY_ID,
        copied_ids=copied_ids,
    )


@app.get("/miqaats/new")
@auth.login_required
def new_miqaat_form():
    return render_template(
        "miqaat_form.html",
        month_names=MONTH_NAMES,
        weekday_names=miqaats.WEEKDAY_NAMES,
        error=None,
        form={},
    )


@app.post("/miqaats/new")
@auth.login_required
def create_miqaat():
    form = request.form
    title = form.get("title", "").strip()
    description = form.get("description", "").strip()
    phase = form.get("phase", "day")
    recurrence_type = form.get("recurrence_type", "hijri")

    errors = []
    if not title:
        errors.append("Title is required.")
    if phase not in ("day", "night"):
        errors.append("Phase must be day or night.")

    hijri_month = hijri_day = weekday = None
    if recurrence_type == "hijri":
        hijri_month = form.get("hijri_month", type=int)
        hijri_day = form.get("hijri_day", type=int)
        if hijri_month is None or not (0 <= hijri_month <= 11):
            errors.append("Pick a valid Hijri month.")
        else:
            max_day = days_in_month(2, hijri_month)  # year=2 is a Kabisa year, so Zilhaj allows 30
            if hijri_day is None or not (1 <= hijri_day <= max_day):
                errors.append(f"Hijri day must be between 1 and {max_day} for {MONTH_NAMES[hijri_month]}.")
    elif recurrence_type == "weekly":
        weekday = form.get("weekday", type=int)
        if weekday is None or not (0 <= weekday <= 6):
            errors.append("Pick a valid day of week.")
    else:
        errors.append("Invalid recurrence type.")

    if errors:
        return render_template(
            "miqaat_form.html",
            month_names=MONTH_NAMES,
            weekday_names=miqaats.WEEKDAY_NAMES,
            error=" ".join(errors),
            form=form,
        ), 400

    miqaats.create_hosted(
        title=title,
        description=description or None,
        phase=phase,
        recurrence_type=recurrence_type,
        hijri_month=hijri_month,
        hijri_day=hijri_day,
        weekday=weekday,
    )
    return redirect(url_for("index", priority=miqaats.HOSTED_PRIORITY_ID))


@app.post("/miqaats/<doc_id>/copy-to-hosted")
@auth.login_required
def copy_miqaat_to_hosted(doc_id: str):
    try:
        miqaats.copy_to_hosted(doc_id)
    except (ValueError, db.ForeignKeyError) as exc:
        return str(exc), 400

    year = request.form.get("year", type=int)
    raw_priority = request.form.get("priority", "")
    city_id = request.form.get("city_id", "")
    return redirect(url_for("index", year=year, priority=raw_priority, city_id=city_id))


@app.post("/miqaats/<doc_id>/remove")
@auth.login_required
def remove_hosted_miqaat(doc_id: str):
    try:
        miqaats.remove_hosted(doc_id)
    except ValueError as exc:
        return str(exc), 400

    year = request.form.get("year", type=int)
    raw_priority = request.form.get("priority", "")
    city_id = request.form.get("city_id", "")
    return redirect(url_for("index", year=year, priority=raw_priority, city_id=city_id))


@app.get("/download.csv")
@auth.login_required
def download_csv():
    hijri_year, priority, city = _resolve_year_view_args()
    entries = _year_payload(hijri_year, priority, city)
    priority_names = {pid: p["name"] for pid, p in db.all_priorities().items()}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Gregorian Date", "Day", "Hijri Date", "Sunrise", "Sunset",
        "Miqaat", "Description", "Phase", "Priority", "Priority Name",
    ])
    for entry in entries:
        hijri = entry["hijri_date"]
        hijri_str = f"{hijri['day']} {hijri['month_name']} {hijri['year']}H"
        sun_times = entry.get("sun") or {}
        for m in entry["miqaats"]:
            writer.writerow([
                entry["gregorian_date"], entry["day_name"], hijri_str,
                sun_times.get("sunrise") or "", sun_times.get("sunset") or "",
                m["title"], m["description"] or "", m["phase"], m["priority_id"],
                priority_names.get(m["priority_id"], ""),
            ])

    filename = f"miqat-list-{hijri_year}H.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/cities")
@auth.login_required
def api_cities():
    query = request.args.get("q", "")
    return jsonify(cities.search_cities(query))


@app.get("/api/miqats/today")
@auth.login_required
def api_today():
    priority = _parse_priority(request.args.get("priority"))
    city = _resolve_city() if "city_id" in request.args else None
    return jsonify(_day_payload(date.today(), priority, city))


@app.get("/api/miqats/year/<int:year>")
@auth.login_required
def api_by_year(year: int):
    priority = _parse_priority(request.args.get("priority"))
    city = _resolve_city() if "city_id" in request.args else None
    return jsonify(_year_payload(year, priority, city))


@app.get("/api/miqats/<iso_date>")
@auth.login_required
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
