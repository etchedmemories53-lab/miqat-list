"""Read-only database browser - local dev only.

Registered in app.py only when FIRESTORE_EMULATOR_HOST is set, so these
routes don't exist at all when this code runs on Cloud Run (which never
sets that env var - production auth goes through the attached service
account instead). No write actions here on purpose, just browsing: the
point is to explore the database, not to give a public URL a second way
to mutate it.
"""

from __future__ import annotations

from flask import Blueprint, render_template, request

import auth
import db

bp = Blueprint("admin", __name__, url_prefix="/admin")
bp.before_request(auth.admin_required(lambda: None))

OPERATORS = ["==", "!=", "<", "<=", ">", ">=", "array-contains"]


def _candidate_values(value: str) -> list:
    """Every plausible type this input could be stored as.

    This tool doesn't know each field's real type ahead of time (e.g.
    priority_id is the string "1", not the int 1) - rather than guess wrong
    and silently return nothing, try every reasonable interpretation and let
    the query results speak for themselves.
    """
    if value == "":
        return [value]
    if value.lower() == "true":
        return [True]
    if value.lower() == "false":
        return [False]
    if value.lower() in ("null", "none"):
        return [None]

    candidates = [value]
    try:
        candidates.append(int(value))
    except ValueError:
        pass
    try:
        candidates.append(float(value))
    except ValueError:
        pass
    return candidates


@bp.get("/")
def index():
    collections = []
    for coll in db.client().collections():
        count = sum(1 for _ in coll.stream())
        collections.append({"name": coll.id, "count": count})
    collections.sort(key=lambda c: c["name"])
    return render_template("admin_index.html", collections=collections)


@bp.get("/<collection>")
def browse_collection(collection: str):
    field = request.args.get("field", "").strip()
    operator = request.args.get("operator", "==")
    raw_value = request.args.get("value", "")
    filtered = bool(field)

    docs = []
    error = None
    try:
        if filtered:
            # Try every plausible type for the typed value and merge by doc
            # id, since a mistyped field/operator/type combo just silently
            # returns zero rows rather than erroring.
            by_id = {}
            for candidate in _candidate_values(raw_value):
                query = db.client().collection(collection).where(field, operator, candidate)
                for doc in query.stream():
                    by_id[doc.id] = {"id": doc.id, "data": doc.to_dict()}
            docs = list(by_id.values())
        else:
            docs = [{"id": doc.id, "data": doc.to_dict()} for doc in db.client().collection(collection).stream()]
        docs.sort(key=lambda d: d["id"])
    except Exception as exc:
        # Anything here (bad field, type mismatch, missing index) is a
        # diagnostic dead-end for whoever's exploring, not a real error to
        # hide - surface it instead of a 500.
        error = f"Query failed: {exc}"

    return render_template(
        "admin_collection.html",
        collection=collection,
        docs=docs,
        field=field,
        operator=operator,
        value=raw_value,
        operators=OPERATORS,
        filtered=filtered,
        error=error,
    )
