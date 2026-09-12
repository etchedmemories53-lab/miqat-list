import calendar as pycal
import csv
import io
import os
from datetime import date, datetime, timedelta

from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

import access_requests
import auth
import cities
import db
import invoice_pdf
import mailer
import miqaats
import niyaz
import org_info
import personal_functions
import settings
import sun
from hijri import MONTH_NAMES, HijriDate, days_in_month

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]

# Cloud Run terminates TLS at its own load balancer and forwards plain HTTP
# to the container, setting X-Forwarded-Proto/Host instead - without this,
# url_for(_external=True) (used to build the OAuth redirect_uri) sees the
# request as http:// and builds a redirect_uri that no longer matches the
# https:// one registered with Google, failing with redirect_uri_mismatch.
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

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

DEFAULT_PRIORITY = miqaats.HOSTED_PRIORITY_ID  # ASChicago Hosted, so the jamaat's own list is what loads by default


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


def _hijri_label(iso_date: str) -> str:
    hijri = HijriDate.from_gregorian(datetime.strptime(iso_date, "%Y-%m-%d").date())
    return f"{hijri.day} {hijri.month_name} {hijri.year}H"


def _hijri_payload(hijri: HijriDate) -> dict:
    return {
        "year": hijri.year,
        "month": hijri.month,
        "month_name": hijri.month_name,
        "month_name_short": hijri.month_name_short,
        "day": hijri.day,
    }


_GENERIC_RECURRENCE_TYPES = ("weekly", "hijri_range")


def _merge_weekly_duplicates(entries: list[dict]) -> list[dict]:
    """Fold a generic recurring entry - a weekly "Jumeraat Majalis", or a
    date-range host miqaat like "Ashara Mubaraka" (1-10 Moharram) - into
    whichever specific-date miqaat lands on the same day, instead of listing
    both. A specific miqaat's own majalis that day already covers the
    generic recurring one (the standing Thursday majalis, or that day's
    Ashara majalis), so showing them as two separate rows overstates what's
    actually happening that day.
    """
    generic = [e for e in entries if e.get("recurrence_type") in _GENERIC_RECURRENCE_TYPES]
    specific = [e for e in entries if e.get("recurrence_type") not in _GENERIC_RECURRENCE_TYPES]
    if not generic or not specific:
        return entries

    merged = [dict(e) for e in specific]
    merged[0]["combined_with"] = ", ".join(g["title"] for g in generic)
    return merged


def _day_payload(gregorian: date, priority: str | None, city: dict | None) -> dict:
    hijri = HijriDate.from_gregorian(gregorian)
    entries = _merge_weekly_duplicates(
        miqaats.for_hijri_date(hijri, priority=priority)
        + miqaats.for_hijri_range(hijri, priority=priority)
        + miqaats.for_weekday(gregorian.weekday(), priority=priority)
    ) + personal_functions.for_date(gregorian.isoformat())
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
    range_index = miqaats.load_hijri_range_index(hijri_year, priority=priority)
    weekly_index = miqaats.load_weekly_index(priority=priority)
    day = HijriDate(hijri_year, 0, 1).to_gregorian()
    end = HijriDate(hijri_year, 11, days_in_month(hijri_year, 11)).to_gregorian()
    personal_index = personal_functions.load_for_range(day.isoformat(), end.isoformat())
    results = []
    while day <= end:
        hijri = HijriDate.from_gregorian(day)
        entries = _merge_weekly_duplicates(
            index.get((hijri.month, hijri.day), [])
            + range_index.get((hijri.month, hijri.day), [])
            + weekly_index.get(day.weekday(), [])
        ) + personal_index.get(day.isoformat(), [])
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


def _month_payload(year: int, month: int) -> dict[str, list[dict]]:
    """iso date -> merged entries for every day in this Gregorian month -
    ASChicago Hosted miqaats and personal functions only, for the Calendar
    view (which is scoped narrower than the main list on purpose)."""
    days_in_month = pycal.monthrange(year, month)[1]
    weekly_index = miqaats.load_weekly_index(priority=miqaats.HOSTED_PRIORITY_ID)
    start = date(year, month, 1)
    end = date(year, month, days_in_month)
    personal_index = personal_functions.load_for_range(start.isoformat(), end.isoformat())

    result = {}
    for day_num in range(1, days_in_month + 1):
        day = date(year, month, day_num)
        hijri = HijriDate.from_gregorian(day)
        entries = _merge_weekly_duplicates(
            miqaats.for_hijri_date(hijri, priority=miqaats.HOSTED_PRIORITY_ID)
            + miqaats.for_hijri_range(hijri, priority=miqaats.HOSTED_PRIORITY_ID)
            + weekly_index.get(day.weekday(), [])
        ) + personal_index.get(day.isoformat(), [])
        if entries:
            result[day.isoformat()] = entries
    return result


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
    niyaz_summaries = niyaz.summary_index()

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
        niyaz_summaries=niyaz_summaries,
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
        personal_error=None,
        personal_form={},
        personal_types=personal_functions.TYPE_LABELS,
        active_tab="miqaat",
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

    hijri_month = hijri_day = weekday = end_hijri_month = end_hijri_day = None
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
    elif recurrence_type == "hijri_range":
        hijri_month = form.get("range_start_month", type=int)
        hijri_day = form.get("range_start_day", type=int)
        end_hijri_month = form.get("range_end_month", type=int)
        end_hijri_day = form.get("range_end_day", type=int)

        if hijri_month is None or not (0 <= hijri_month <= 11):
            errors.append("Pick a valid start Hijri month.")
        if end_hijri_month is None or not (0 <= end_hijri_month <= 11):
            errors.append("Pick a valid end Hijri month.")

        if not errors:
            start_max_day = days_in_month(2, hijri_month)
            end_max_day = days_in_month(2, end_hijri_month)
            if hijri_day is None or not (1 <= hijri_day <= start_max_day):
                errors.append(f"Start day must be between 1 and {start_max_day} for {MONTH_NAMES[hijri_month]}.")
            if end_hijri_day is None or not (1 <= end_hijri_day <= end_max_day):
                errors.append(f"End day must be between 1 and {end_max_day} for {MONTH_NAMES[end_hijri_month]}.")

        if not errors:
            start_doy = HijriDate(2, hijri_month, hijri_day).day_of_year()
            end_doy = HijriDate(2, end_hijri_month, end_hijri_day).day_of_year()
            if end_doy < start_doy:
                errors.append("End date must be on or after the start date within the same Hijri year.")
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
        end_hijri_month=end_hijri_month,
        end_hijri_day=end_hijri_day,
    )
    return redirect(url_for("index", priority=miqaats.HOSTED_PRIORITY_ID))


@app.post("/personal-functions/new")
@auth.login_required
def create_personal_function():
    form = request.form
    type_ = form.get("type", "")
    custom_type = form.get("custom_type", "").strip()
    details = form.get("details", "").strip()
    date_str = form.get("date", "")

    errors = []
    if type_ not in personal_functions.TYPE_LABELS:
        errors.append("Pick a valid function type.")
    if type_ == "other" and not custom_type:
        errors.append("Enter a custom type name.")

    gregorian = None
    if not date_str:
        errors.append("Date is required.")
    else:
        try:
            gregorian = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            errors.append("Date must be a valid date.")

    if errors:
        return render_template(
            "miqaat_form.html",
            month_names=MONTH_NAMES,
            weekday_names=miqaats.WEEKDAY_NAMES,
            error=None,
            form={},
            personal_error=" ".join(errors),
            personal_form=form,
            personal_types=personal_functions.TYPE_LABELS,
            active_tab="personal",
        ), 400

    personal_functions.create(type_, custom_type or None, details or None, gregorian)
    return redirect(url_for("index", year=HijriDate.from_gregorian(gregorian).year))


@app.post("/personal-functions/<function_id>/remove")
@auth.login_required
def remove_personal_function(function_id: str):
    try:
        personal_functions.remove(function_id)
    except ValueError as exc:
        return str(exc), 400

    year = request.form.get("year", type=int)
    raw_priority = request.form.get("priority", "")
    city_id = request.form.get("city_id", "")
    return redirect(url_for("index", year=year, priority=raw_priority, city_id=city_id))


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


@app.get("/miqaats/<miqaat_id>/niyaz/<gregorian_date>")
@auth.login_required
def niyaz_form(miqaat_id: str, gregorian_date: str):
    try:
        datetime.strptime(gregorian_date, "%Y-%m-%d")
    except ValueError:
        return "date must be in YYYY-MM-DD format", 400

    snap = db.client().collection(db.MIQAATS).document(miqaat_id).get()
    if not snap.exists:
        return "miqaat not found", 404

    record = niyaz.get(miqaat_id, gregorian_date)
    line_items = (record or {}).get("line_items") or [{"label": name, "amount": None} for name in niyaz.get_default_line_item_labels()]

    return render_template(
        "niyaz_form.html",
        miqaat_id=miqaat_id,
        miqaat_title=snap.to_dict().get("title", ""),
        gregorian_date=gregorian_date,
        record=record,
        line_items=line_items,
        error=None,
        year=request.args.get("year", type=int),
        priority=request.args.get("priority", ""),
        city_id=request.args.get("city_id", ""),
    )


@app.post("/miqaats/<miqaat_id>/niyaz/<gregorian_date>")
@auth.login_required
def save_niyaz(miqaat_id: str, gregorian_date: str):
    try:
        datetime.strptime(gregorian_date, "%Y-%m-%d")
    except ValueError:
        return "date must be in YYYY-MM-DD format", 400

    snap = db.client().collection(db.MIQAATS).document(miqaat_id).get()
    if not snap.exists:
        return "miqaat not found", 404
    miqaat_title = snap.to_dict().get("title", "")

    form = request.form
    host_name = form.get("host_name", "").strip()
    host_its = form.get("host_its", "").strip()
    host_email = form.get("host_email", "").strip()
    host_phone = form.get("host_phone", "").strip()
    thals = form.get("thals", type=int)

    line_items = []
    for label, amount in zip(form.getlist("item_label"), form.getlist("item_amount")):
        label = label.strip()
        if not label:
            continue
        try:
            amount_val = float(amount) if amount.strip() else 0.0
        except ValueError:
            amount_val = 0.0
        line_items.append({"label": label, "amount": amount_val})

    errors = niyaz.validate(host_name, host_its, host_email, host_phone, thals, line_items)
    if errors:
        return render_template(
            "niyaz_form.html",
            miqaat_id=miqaat_id,
            miqaat_title=miqaat_title,
            gregorian_date=gregorian_date,
            record={"host_name": host_name, "host_its": host_its, "host_email": host_email, "host_phone": host_phone, "thals": thals},
            line_items=line_items or [{"label": name, "amount": None} for name in niyaz.get_default_line_item_labels()],
            error=" ".join(errors),
            year=form.get("year", type=int),
            priority=form.get("priority", ""),
            city_id=form.get("city_id", ""),
        ), 400

    niyaz.save(
        miqaat_id,
        gregorian_date,
        thals=thals,
        host_name=host_name,
        host_its=host_its,
        host_email=host_email,
        host_phone=host_phone,
        line_items=line_items,
    )

    return redirect(url_for(
        "index",
        year=form.get("year", type=int),
        priority=form.get("priority", ""),
        city_id=form.get("city_id", ""),
    ))


@app.post("/miqaats/<miqaat_id>/niyaz/<gregorian_date>/delete")
@auth.login_required
def delete_niyaz(miqaat_id: str, gregorian_date: str):
    niyaz.delete(miqaat_id, gregorian_date)
    return redirect(url_for(
        "index",
        year=request.form.get("year", type=int),
        priority=request.form.get("priority", ""),
        city_id=request.form.get("city_id", ""),
    ))


@app.get("/miqaats/<miqaat_id>/niyaz/<gregorian_date>/invoice")
@auth.login_required
def niyaz_invoice(miqaat_id: str, gregorian_date: str):
    snap = db.client().collection(db.MIQAATS).document(miqaat_id).get()
    if not snap.exists:
        return "miqaat not found", 404
    record = niyaz.get(miqaat_id, gregorian_date)
    if not record:
        return redirect(url_for("niyaz_form", miqaat_id=miqaat_id, gregorian_date=gregorian_date))

    return render_template(
        "niyaz_invoice.html",
        miqaat_id=miqaat_id,
        miqaat_title=snap.to_dict().get("title", ""),
        gregorian_date=gregorian_date,
        hijri_date=_hijri_label(gregorian_date),
        record=record,
        total_cost=niyaz.total_cost(record.get("line_items") or []),
        cost_per_thal=niyaz.cost_per_thal(record.get("line_items") or [], record.get("thals")),
        org_name=org_info.NAME,
        org_address_lines=org_info.ADDRESS_LINES,
        share_link=None,
        share_password=None,
        mail_error=request.args.get("mail_error"),
        mail_sent=request.args.get("mail_sent"),
        year=request.args.get("year", type=int),
        priority=request.args.get("priority", ""),
        city_id=request.args.get("city_id", ""),
    )


@app.get("/miqaats/<miqaat_id>/niyaz/<gregorian_date>/invoice.pdf")
@auth.login_required
def niyaz_invoice_pdf(miqaat_id: str, gregorian_date: str):
    snap = db.client().collection(db.MIQAATS).document(miqaat_id).get()
    if not snap.exists:
        return "miqaat not found", 404
    record = niyaz.get(miqaat_id, gregorian_date)
    if not record:
        return "no Niyaz record for this date", 404

    pdf_bytes = invoice_pdf.build(snap.to_dict().get("title", ""), gregorian_date, record)
    filename = f"niyaz-invoice-{gregorian_date}.pdf"
    return Response(pdf_bytes, mimetype="application/pdf", headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.post("/miqaats/<miqaat_id>/niyaz/<gregorian_date>/email")
@auth.login_required
def niyaz_invoice_email(miqaat_id: str, gregorian_date: str):
    snap = db.client().collection(db.MIQAATS).document(miqaat_id).get()
    if not snap.exists:
        return "miqaat not found", 404
    record = niyaz.get(miqaat_id, gregorian_date)
    if not record:
        return "no Niyaz record for this date", 404

    miqaat_title = snap.to_dict().get("title", "")
    try:
        mailer.send_invoice(record["host_email"], miqaat_title, gregorian_date, _hijri_label(gregorian_date), record)
    except mailer.NotConfigured as exc:
        return redirect(url_for("niyaz_invoice", miqaat_id=miqaat_id, gregorian_date=gregorian_date, mail_error=str(exc)))
    except Exception as exc:
        return redirect(url_for("niyaz_invoice", miqaat_id=miqaat_id, gregorian_date=gregorian_date, mail_error=f"Failed to send: {exc}"))

    return redirect(url_for("niyaz_invoice", miqaat_id=miqaat_id, gregorian_date=gregorian_date, mail_sent="1"))


@app.post("/miqaats/<miqaat_id>/niyaz/<gregorian_date>/share")
@auth.login_required
def niyaz_invoice_share(miqaat_id: str, gregorian_date: str):
    snap = db.client().collection(db.MIQAATS).document(miqaat_id).get()
    if not snap.exists:
        return "miqaat not found", 404
    if not niyaz.get(miqaat_id, gregorian_date):
        return "no Niyaz record for this date", 404

    token, password = niyaz.create_share(miqaat_id, gregorian_date)
    record = niyaz.get(miqaat_id, gregorian_date)

    return render_template(
        "niyaz_invoice.html",
        miqaat_id=miqaat_id,
        miqaat_title=snap.to_dict().get("title", ""),
        gregorian_date=gregorian_date,
        hijri_date=_hijri_label(gregorian_date),
        record=record,
        total_cost=niyaz.total_cost(record.get("line_items") or []),
        cost_per_thal=niyaz.cost_per_thal(record.get("line_items") or [], record.get("thals")),
        org_name=org_info.NAME,
        org_address_lines=org_info.ADDRESS_LINES,
        share_link=url_for("public_invoice", token=token, _external=True),
        share_password=password,
        mail_error=None,
        mail_sent=None,
        year=request.form.get("year", type=int),
        priority=request.form.get("priority", ""),
        city_id=request.form.get("city_id", ""),
    )


def _public_invoice_context(record: dict) -> dict:
    snap = db.client().collection(db.MIQAATS).document(record["miqaat_id"]).get()
    return {
        "miqaat_title": snap.to_dict().get("title", "") if snap.exists else "",
        "gregorian_date": record["gregorian_date"],
        "hijri_date": _hijri_label(record["gregorian_date"]),
        "record": record,
        "total_cost": niyaz.total_cost(record.get("line_items") or []),
        "cost_per_thal": niyaz.cost_per_thal(record.get("line_items") or [], record.get("thals")),
        "org_name": org_info.NAME,
        "org_address_lines": org_info.ADDRESS_LINES,
    }


@app.get("/invoice/<token>")
def public_invoice(token: str):
    record = niyaz.get_by_token(token)
    if not record:
        return "This link is no longer valid.", 404
    if not session.get(f"invoice_access_{token}"):
        return render_template("public_invoice_login.html", token=token, error=None)
    return render_template("public_invoice.html", token=token, **_public_invoice_context(record))


@app.post("/invoice/<token>")
def public_invoice_login(token: str):
    record = niyaz.get_by_token(token)
    if not record:
        return "This link is no longer valid.", 404
    if not niyaz.verify_share_password(record, request.form.get("password", "")):
        return render_template("public_invoice_login.html", token=token, error="Incorrect password."), 400

    session[f"invoice_access_{token}"] = True
    return render_template("public_invoice.html", token=token, **_public_invoice_context(record))


@app.get("/invoice/<token>/pdf")
def public_invoice_pdf(token: str):
    record = niyaz.get_by_token(token)
    if not record or not session.get(f"invoice_access_{token}"):
        return "Not authorized.", 403

    context = _public_invoice_context(record)
    pdf_bytes = invoice_pdf.build(context["miqaat_title"], context["gregorian_date"], record)
    filename = f"niyaz-invoice-{context['gregorian_date']}.pdf"
    return Response(pdf_bytes, mimetype="application/pdf", headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.get("/calendar")
@auth.login_required
def calendar_view():
    today = date.today()
    year = request.args.get("year", type=int) or today.year
    month = request.args.get("month", type=int) or today.month
    month = max(1, min(12, month))

    entries_by_date = _month_payload(year, month)
    weeks = []
    for week in pycal.Calendar(firstweekday=6).monthdayscalendar(year, month):
        row = []
        for day_num in week:
            if day_num == 0:
                row.append(None)
            else:
                day = date(year, month, day_num)
                iso = day.isoformat()
                row.append({
                    "day": day_num,
                    "iso": iso,
                    "entries": entries_by_date.get(iso, []),
                    "hijri_year": HijriDate.from_gregorian(day).year,
                })
        weeks.append(row)

    prev_month, prev_year = (12, year - 1) if month == 1 else (month - 1, year)
    next_month, next_year = (1, year + 1) if month == 12 else (month + 1, year)

    return render_template(
        "calendar.html",
        year=year,
        month=month,
        month_name=date(year, month, 1).strftime("%B"),
        prev_year=prev_year, prev_month=prev_month, prev_month_name=date(prev_year, prev_month, 1).strftime("%B"),
        next_year=next_year, next_month=next_month, next_month_name=date(next_year, next_month, 1).strftime("%B"),
        weeks=weeks,
        weekday_headers=["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        today_iso=today.isoformat(),
    )


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
