# miqat-list

Flask app that lists Dawoodi Bohra miqaats (and lesser urus observances) for
a Hijri year, with Gregorian date, day of week, and (given a city)
sunrise/sunset for that day.

Ported from [mumineen_calendar_js](https://github.com/mygulamali/mumineen_calendar_js) (MIT):
- `hijri.py` — the tabular Hijri<->Gregorian conversion (`_lib/hijri_date.js`), both directions
- `data/miqaats.json` — the miqaat/urus dataset (`source/data/miqaats.json`), unchanged
- `priority == 1` matches that app's "miqat" (sun/moon icon); `2`/`3` are lesser urus (dot icon)

City search (`cities.py`) and sunrise/sunset (`sun.py`) are both computed
entirely offline — no external API calls at request time:
- `geonamescache` bundles ~34k cities with lat/lon/timezone
- `astral` computes sunrise/sunset from that lat/lon/timezone via standard
  solar-position math

## Run locally

```
./docker-run.sh -p 8080
```
or manually:
```
docker build -t miqat-list .
docker run --rm -p 8080:8080 miqat-list
```

Then open http://localhost:8080

## API

- `GET /api/miqats/today?priority=1&city_id=1275339`
- `GET /api/miqats/2026-09-07?priority=1&city_id=1275339` (Gregorian date)
- `GET /api/miqats/year/1448?priority=1&city_id=1275339` (Hijri year)
- `GET /api/cities?q=london`

`priority` and `city_id` are optional. Omit `priority` for all entries;
omit `city_id` to skip sunrise/sunset. City ids come from `/api/cities`.

## Deploy

Dockerized for Google Cloud Run, deployed automatically by
`.github/workflows/deploy.yml` on every push to `master` (or manually via the
Actions tab's "Run workflow"), using Workload Identity Federation — no stored
GCP key in GitHub.

One-time setup, before the first deploy will work:
1. Run `./gcp/setup.sh` once (locally or in Cloud Shell, with `gcloud`
   authenticated to the target project) — creates the Artifact Registry repo,
   the runtime service account, and a repo-scoped Workload Identity Provider.
2. Set the GitHub repo variables it prints (Settings > Secrets and variables
   > Actions > Variables) — already done for this repo; re-run only needed if
   the project/resources are ever recreated.

The service has no secrets or external APIs, so it deploys with
`--allow-unauthenticated` and no `secrets:` block.
