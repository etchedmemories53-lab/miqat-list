# miqat-list

Flask app that lists Dawoodi Bohra miqaats (and lesser urus observances) for
a Hijri year, with Gregorian date, day of week, and (given a city)
sunrise/sunset for that day.

Ported from [mumineen_calendar_js](https://github.com/mygulamali/mumineen_calendar_js) (MIT):
- `hijri.py` — the tabular Hijri<->Gregorian conversion (`_lib/hijri_date.js`), both directions
- `data/miqaats.json` — the miqaat/urus dataset (`source/data/miqaats.json`), unchanged, now only
  used as seed data for Firestore (see below) rather than read directly at runtime
- `priority == 1` matches that app's "miqat" (sun/moon icon); `2`/`3` are lesser urus (dot icon).
  `4` ("ASChicago Hosted") is local to this app — any miqaat can be copied into it from the UI,
  and any signed-in user can also author a brand new one directly ("+ Add Miqat/Majalis" on the
  home page), recurring either on a specific Hijri date every year or on a day of the week every
  week (e.g. a weekly Friday night majalis) — see Data: Firestore, below.

City search (`cities.py`) and sunrise/sunset (`sun.py`) are both computed
entirely offline — no external API calls at request time:
- `geonamescache` bundles ~34k cities with lat/lon/timezone
- `astral` computes sunrise/sunset from that lat/lon/timezone via standard
  solar-position math

## Data: Firestore

`priorities` and `miqaats` are Firestore collections (`db.py`, `miqaats.py`) —
each miqaat document has a `priority_id` field that's meant to work like a
foreign key into `priorities/{id}`. Firestore itself doesn't enforce that
(no schema, no FK constraints), so `db.require_priority()` is where it's
enforced instead: every write that sets a priority_id goes through it first
and raises `db.ForeignKeyError` if that priority doesn't exist.

Every `miqaats` document also has a `recurrence_type`: `"hijri"` (the
default — matches on `hijri_month`/`hijri_day`, every Hijri year) or
`"weekly"` (matches on `weekday`, 0=Monday..6=Sunday, every Gregorian week —
user-added only, via "+ Add Miqat/Majalis"). `miqaats.load_year_index()` and
`miqaats.load_weekly_index()` are queried separately and merged per day in
`app.py`'s `_year_payload`/`_day_payload`, since a weekly row has no
Hijri date to index by.

Auth is never a password, in either environment:
- **Locally**: `FIRESTORE_EMULATOR_HOST` points the client at the emulator,
  which doesn't check credentials at all.
- **Cloud Run**: with that env var unset, the client authenticates as the
  container's attached service account via Application Default Credentials.

## Auth: Google sign-in + self-service access requests

Every route requires a Google sign-in (`auth.py`) — enforced by the app
itself, not Cloud Run's IAM layer (that only understands Google IAM
principals, not an arbitrary Google account with an email allowlist), so
Cloud Run stays `--allow-unauthenticated` at the ingress level while the app
gates access on top of it. No passwords anywhere: it's a standard OAuth 2.0 /
OpenID Connect flow against Google, same code path locally and in prod.

Two tiers of access:
- **Bootstrap admins** — emails in the `ALLOWED_EMAILS` env var. Always let
  in, and the only accounts that can reach **Settings** (nav bar, top
  right). This exists so there's always at least one account that can
  approve everyone else, even before Firestore has any requests in it.
- **Everyone else** — any other Google account that signs in lands in the
  `access_requests` Firestore collection (`access_requests.py`) as
  `pending`, and sees a "request sent" page instead of the app. An admin
  reviews pending/approved/denied requests and approves or denies them from
  **Settings > Access Requests** — no env var edits or redeploys needed for
  that part; it's just a Firestore write.

Required env vars (see `.env.example`):
- `SECRET_KEY` — signs the Flask session cookie. Any random value works
  (`openssl rand -hex 32`); it just needs to stay stable so sessions survive
  restarts, and secret so cookies can't be forged.
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — a Google OAuth 2.0 "Web
  application" client (Google Cloud Console > APIs & Services >
  Credentials). This repo reuses the client already created for
  etched-memories-app, since it's the same GCP project.
- `ALLOWED_EMAILS` — comma-separated list of bootstrap admin emails. Leave
  empty/unset and no one can reach Settings to approve anyone — set at
  least your own email.

**One manual step, per environment**: the OAuth client's "Authorized
redirect URIs" list (Console > Credentials > this client) must include this
app's exact callback URL, or Google rejects the login with
`redirect_uri_mismatch`:
- Local: `http://localhost:8080/auth/callback`
- Cloud Run: `https://<the-deployed-service-url>/auth/callback`

There's no API for editing that list — it's a one-time manual add in the
Console for each URL.

## Run locally

```
cp .env.example .env   # then fill in SECRET_KEY / GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / ALLOWED_EMAILS
docker compose up -d firestore-emulator app
docker compose --profile tools run --rm seed   # one-off: loads data/miqaats.json in
```

Then open http://localhost:8080 and sign in with an allowed Google account.
Re-running `seed` is safe — it overwrites the same deterministic document ids
rather than duplicating them (though any already-copied "ASChicago Hosted"
entries are untouched, since those get random ids).

Every route reads from Firestore now (there's no JSON-file fallback), so
`./docker-run.sh` alone needs `FIRESTORE_EMULATOR_HOST` pointed at a running
emulator to do anything useful — `docker compose` is the real local dev path.

### Running against real GCP Firestore instead of the emulator

`docker-compose.gcp.yml` overrides the `app`/`seed` services to talk to the
real Firestore database in `etched-memories-app` instead of the emulator,
authenticating via your own `gcloud auth application-default login` (no
downloaded service-account key). One-time setup and details are documented
in that file.

```bash
./run-gcp.sh
```

Run this from WSL, not Windows-side git-bash/PowerShell — the credentials
volume mount needs `$HOME` to resolve to your Linux home. The script always
tears down first and tears down again on exit/Ctrl+C, and always rebuilds
the image before starting — this machine has two independent Docker engines
(Docker Desktop vs WSL's own `dockerd`) with separate image caches, so
skipping either step risks silently running a stale build left over from
whichever engine you used last.

## API

All routes below require a signed-in session (see Auth, above) — an
anonymous request gets redirected into the Google login flow instead of JSON.

- `GET /api/miqats/today?priority=1&city_id=1275339`
- `GET /api/miqats/2026-09-07?priority=1&city_id=1275339` (Gregorian date)
- `GET /api/miqats/year/1448?priority=1&city_id=1275339` (Hijri year)
- `GET /api/cities?q=london`
- `POST /miqaats/<doc_id>/copy-to-hosted` (form fields `year`, `priority`,
  `city_id`) — copies that miqaat into priority `4` ("ASChicago Hosted") and
  redirects back to the same year/priority/city view.
- `GET /miqaats/new` / `POST /miqaats/new` — form to author a brand new
  miqaat/majalis straight into priority `4`. Form fields: `title`,
  `description` (optional), `phase` (`day`/`night`), `recurrence_type`
  (`hijri`, with `hijri_month` 0-11 + `hijri_day`; or `weekly`, with
  `weekday` 0=Monday..6=Sunday).

`priority` is `1`/`2`/`3`/`4` and optional (omit for all); `city_id` is
optional too (omit to skip sunrise/sunset). City ids come from `/api/cities`.

## Deploy

Dockerized for Google Cloud Run, deployed automatically by
`.github/workflows/deploy.yml` on every push to `master` (or manually via the
Actions tab's "Run workflow"), using Workload Identity Federation — no stored
GCP key in GitHub.

**Not deploy-ready as-is anymore**: the deployed Cloud Run service has no
Firestore database, and its runtime service account has no `datastore.user`
role — both were only set up for the local emulator so far. Deploying the
current code would 500 on every request. Wiring this up for real would mean
extending `gcp/setup.sh` with a one-time `gcloud firestore databases create`
and granting `miqat-list-runtime` `roles/datastore.user`, then running
`scripts/seed_firestore.py` once against the real project.

One-time setup this repo already has, before *that* first deploy will work:
1. Run `./gcp/setup.sh` once (locally or in Cloud Shell, with `gcloud`
   authenticated to the target project) — creates the Artifact Registry repo,
   the runtime service account, and a repo-scoped Workload Identity Provider.
2. Set the GitHub repo variables it prints (Settings > Secrets and variables
   > Actions > Variables) — already done for this repo; re-run only needed if
   the project/resources are ever recreated.

Also needed for Google sign-in in production (`deploy.yml` passes these
through as the Cloud Run service's env vars):
- Repo **variables**: `GOOGLE_CLIENT_ID`, `ALLOWED_EMAILS`
- Repo **secrets**: `GOOGLE_CLIENT_SECRET`, `APP_SECRET_KEY`

And once the Cloud Run URL is known, add
`https://<that-url>/auth/callback` to the OAuth client's authorized redirect
URIs in the Console (see Auth, above) — login will fail with
`redirect_uri_mismatch` until that's done.
