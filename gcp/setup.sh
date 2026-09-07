#!/usr/bin/env bash
# One-time setup: creates everything GitHub Actions needs to build and deploy
# this app to Cloud Run via Workload Identity Federation (no stored key).
#
# Reuses the shared "github-deployer" service account and "github-pool" from
# the etched-memories-app project (see etched-memories-wp/gcp/setup.sh for
# where those first got created) — this script only adds what's new for
# miqat-list: its own Artifact Registry repo, its own runtime service
# account, and its own repo-scoped Workload Identity Provider.
#
# Run this once, locally or in Cloud Shell, with `gcloud` already authenticated
# to the target project (`gcloud auth login` and `gcloud config set project ...`).
#
# Usage: ./gcp/setup.sh
set -euo pipefail

# ---- fill these in before running ----
PROJECT_ID="etched-memories-app"
REGION="us-central1"
REPOSITORY="miqat-list"                  # Artifact Registry repo name
SERVICE_ACCOUNT_NAME="github-deployer"   # shared across apps in this project
RUNTIME_SERVICE_ACCOUNT_NAME="miqat-list-runtime"
POOL_NAME="github-pool"                  # shared across apps in this project
PROVIDER_NAME="github-provider-miqat-list"
GITHUB_REPO="etchedmemories53-lab/miqat-list"
# ---------------------------------------

SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
RUNTIME_SERVICE_ACCOUNT_EMAIL="${RUNTIME_SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "==> Enabling required APIs..."
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  iamcredentials.googleapis.com \
  iam.googleapis.com \
  --project="$PROJECT_ID"

echo "==> Creating Artifact Registry repository..."
if gcloud artifacts repositories describe "$REPOSITORY" --project="$PROJECT_ID" --location="$REGION" >/dev/null 2>&1; then
  echo "  (already exists, skipping)"
else
  gcloud artifacts repositories create "$REPOSITORY" \
    --project="$PROJECT_ID" \
    --repository-format=docker \
    --location="$REGION" \
    --description="Miqat List"
fi

echo "==> Ensuring GitHub Actions deployer service account exists..."
if gcloud iam service-accounts describe "$SERVICE_ACCOUNT_EMAIL" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "  (already exists, skipping - reused from other apps in this project)"
else
  gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
    --project="$PROJECT_ID" \
    --display-name="GitHub Actions Deployer"
fi

echo "==> Granting roles to the GitHub Actions deployer service account..."
for ROLE in run.admin artifactregistry.writer iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/${ROLE}" \
    --condition=None \
    >/dev/null
done

# The deployer account above is who GitHub Actions authenticates as to *perform*
# the deployment — it's not who the app runs as afterward. Cloud Run runs the
# actual container under its own separate "runtime" service account. This app
# has no secrets/external APIs, so this account needs no extra IAM roles beyond
# existing — it's just an identity Cloud Run can attach, scoped to nothing else.
echo "==> Creating runtime service account for the Cloud Run service itself..."
if gcloud iam service-accounts describe "$RUNTIME_SERVICE_ACCOUNT_EMAIL" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "  (already exists, skipping)"
else
  gcloud iam service-accounts create "$RUNTIME_SERVICE_ACCOUNT_NAME" \
    --project="$PROJECT_ID" \
    --display-name="Miqat List Cloud Run runtime"
  # Freshly-created service accounts aren't always immediately visible to other
  # IAM calls yet — binding roles to it right away can fail with "does not
  # exist" otherwise.
  for attempt in 1 2 3 4 5; do
    gcloud iam service-accounts describe "$RUNTIME_SERVICE_ACCOUNT_EMAIL" --project="$PROJECT_ID" >/dev/null 2>&1 && break
    echo "  (not visible yet — retrying...)"
    sleep 5
  done
fi

# The deployer also needs to be able to hand this runtime identity to the
# Cloud Run revision it creates (deploy-cloudrun passes --service-account).
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SERVICE_ACCOUNT_EMAIL" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
  --role="roles/iam.serviceAccountUser" \
  >/dev/null

echo "==> Ensuring Workload Identity Pool exists..."
if gcloud iam workload-identity-pools describe "$POOL_NAME" --project="$PROJECT_ID" --location="global" >/dev/null 2>&1; then
  echo "  (already exists, skipping - reused from other apps in this project)"
else
  gcloud iam workload-identity-pools create "$POOL_NAME" \
    --project="$PROJECT_ID" \
    --location="global" \
    --display-name="GitHub Actions Pool"
fi

echo "==> Creating Workload Identity Provider (scoped to $GITHUB_REPO only)..."
if gcloud iam workload-identity-pools providers describe "$PROVIDER_NAME" --project="$PROJECT_ID" --location="global" --workload-identity-pool="$POOL_NAME" >/dev/null 2>&1; then
  echo "  (already exists, skipping)"
else
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_NAME" \
    --project="$PROJECT_ID" \
    --location="global" \
    --workload-identity-pool="$POOL_NAME" \
    --display-name="GitHub Provider (miqat-list)" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
    --attribute-condition="assertion.repository=='${GITHUB_REPO}'" \
    --issuer-uri="https://token.actions.githubusercontent.com"
fi

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")

echo "==> Allowing GitHub Actions (from $GITHUB_REPO) to impersonate the service account..."
gcloud iam service-accounts add-iam-policy-binding "$SERVICE_ACCOUNT_EMAIL" \
  --project="$PROJECT_ID" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_NAME}/attribute.repository/${GITHUB_REPO}"

echo "==> Fetching the provider's full resource name..."
WIF_PROVIDER=""
for attempt in 1 2 3 4 5; do
  if WIF_PROVIDER=$(gcloud iam workload-identity-pools providers describe "$PROVIDER_NAME" \
    --project="$PROJECT_ID" \
    --location="global" \
    --workload-identity-pool="$POOL_NAME" \
    --format="value(name)" 2>/dev/null); then
    break
  fi
  echo "  (not visible yet — IAM changes can take a few seconds to propagate, retrying...)"
  sleep 5
done
if [ -z "$WIF_PROVIDER" ]; then
  echo "ERROR: still couldn't read back the provider after 5 tries. It was likely" >&2
  echo "created fine — just re-run this script in a minute to pick up where it left off." >&2
  exit 1
fi

echo ""
echo "Done. GitHub repo variables (Settings > Secrets and variables > Actions >"
echo "Variables) should already be set to these — this is just for reference:"
echo ""
echo "  GCP_PROJECT_ID                 = ${PROJECT_ID}"
echo "  GCP_REGION                     = ${REGION}"
echo "  GCP_AR_REPOSITORY              = ${REPOSITORY}"
echo "  GCP_SERVICE_ACCOUNT            = ${SERVICE_ACCOUNT_EMAIL}"
echo "  GCP_RUNTIME_SERVICE_ACCOUNT    = ${RUNTIME_SERVICE_ACCOUNT_EMAIL}"
echo "  GCP_WORKLOAD_IDENTITY_PROVIDER = ${WIF_PROVIDER}"
