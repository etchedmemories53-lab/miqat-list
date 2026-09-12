"""Firestore client, plus the FK-style integrity check Firestore itself has
no concept of.

Firestore has no schema and no foreign keys - nothing stops a `miqaats`
document from pointing at a `priorities` id that doesn't exist. This module
is where that constraint actually gets enforced instead: every write that
sets a priority_id goes through require_priority() first.

Locally (docker-compose), FIRESTORE_EMULATOR_HOST points this at the
emulator with no real credentials at all. In Cloud Run, that env var is
unset, so the client authenticates as the container's attached service
account via Application Default Credentials - no key, no password, either way.
"""

from __future__ import annotations

import os

from google.cloud import firestore

PRIORITIES = "priorities"
MIQAATS = "miqaats"
NIYAZ = "niyaz"
PERSONAL_FUNCTIONS = "personal_functions"

_client: firestore.Client | None = None


class ForeignKeyError(ValueError):
    """A write referenced a priorities/{id} document that doesn't exist."""


def client() -> firestore.Client:
    global _client
    if _client is None:
        project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")
        _client = firestore.Client(project=project) if project else firestore.Client()
    return _client


def get_priority(priority_id: str) -> dict | None:
    snap = client().collection(PRIORITIES).document(priority_id).get()
    return {**snap.to_dict(), "id": snap.id} if snap.exists else None


def priority_exists(priority_id: str) -> bool:
    return client().collection(PRIORITIES).document(priority_id).get().exists


def require_priority(priority_id: str) -> None:
    if not priority_exists(priority_id):
        raise ForeignKeyError(f"priority {priority_id!r} does not exist")


def all_priorities() -> dict[str, dict]:
    """priority_id -> {"id": ..., "name": ...} for every priority."""
    return {doc.id: {**doc.to_dict(), "id": doc.id} for doc in client().collection(PRIORITIES).stream()}
