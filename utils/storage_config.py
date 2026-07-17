"""Contact storage mode — PostgreSQL only for server-side persistence.

IndexedDB remains the offline-queue mechanism on the frontend (browser-side).
"""

import os


def get_contact_storage_mode() -> str:
    """Return the active storage backend.

    When DATABASE_URL is set, contacts are persisted to PostgreSQL.
    Otherwise returns 'indexeddb' (no server-side persistence).
    Firebase / MongoDB are not supported.
    """
    if os.getenv("DATABASE_URL", "").strip():
        return "postgresql"
    return "indexeddb"


def is_client_side_storage() -> bool:
    """True when the backend should NOT persist contacts (no DATABASE_URL)."""
    return get_contact_storage_mode() == "indexeddb"
