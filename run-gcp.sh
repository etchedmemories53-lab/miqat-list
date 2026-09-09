#!/usr/bin/env bash
# Runs the app against the real GCP Firestore database (docker-compose.gcp.yml
# override) instead of the local emulator - see that file for the one-time
# `gcloud auth application-default login` setup it depends on.
#
# Run from WSL specifically, not Windows-side git-bash/PowerShell: the ADC
# volume mount needs $HOME to resolve to your Linux home, and this machine
# has two independent Docker engines (Docker Desktop vs WSL's own dockerd)
# with separate image caches - always tearing down and rebuilding here is
# what guarantees you're never running a stale image left over on whichever
# engine you last used.
#
# Usage: ./run-gcp.sh
set -euo pipefail
cd "$(dirname "$0")"

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.gcp.yml)

cleanup() {
  echo ""
  echo "==> Tearing down..."
  "${COMPOSE[@]}" down
}
trap cleanup EXIT

echo "==> Tearing down any existing containers first (clean slate)..."
"${COMPOSE[@]}" down

echo "==> Building app image..."
"${COMPOSE[@]}" build app

echo "==> Starting app against real GCP Firestore on http://localhost:8080 ..."
echo "    (Ctrl+C to stop and tear down)"
"${COMPOSE[@]}" up --no-deps app
