"""Contact storage mode — PostgreSQL for server-side persistence.

IndexedDB remains the offline-queue mechanism on the frontend (browser-side).
This backend always persists to PostgreSQL when DATABASE_URL is configured.
"""

import os


def get_contact_storage_mode() -> str:
    """Return the active storage backend.

    When DATABASE_URL is set, contacts are persisted to PostgreSQL.
    Otherwise falls back to 'indexeddb' (no server-side persistence).
    """
    if os.getenv("DATABASE_URL", "").strip():
        return "postgresql"
    return "indexeddb"


def is_client_side_storage() -> bool:
    """True when the backend should NOT persist contacts (IndexedDB-only mode)."""
    return get_contact_storage_mode() == "indexeddb"
