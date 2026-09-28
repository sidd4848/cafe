"""Runtime settings, read once from the environment."""

import os

import google.auth


def _default_project() -> str | None:
    """Fall back to the project of the active gcloud / Cloud Run credentials."""
    try:
        return google.auth.default()[1]
    except Exception:
        return None


PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT") or _default_project()
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", PROJECT_ID)
FIRESTORE_DB = os.getenv("FIRESTORE_DB", "cafedata")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_LOCATION = os.getenv("GEMINI_LOCATION", "global")
EMBED_MODEL = os.getenv("EMBED_MODEL", "gemini-embedding-001")
EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))

DEFAULT_CAFE_ID = os.getenv("DEFAULT_CAFE_ID", "koramangala")

# Accounts that become managers the first time they sign in. Everyone else is a customer
# until a manager invites them from the staff console.
BOOTSTRAP_MANAGERS = {
    e.strip().lower() for e in os.getenv("BOOTSTRAP_MANAGERS", "").split(",") if e.strip()
}

ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if o.strip()
]

# Cloud Scheduler calls /internal/* with an OIDC token minted for this service account.
SCHEDULER_SA = os.getenv("SCHEDULER_SA", "")
# Audience the scheduler token must carry; the service's own URL. Blank disables the
# internal routes rather than accepting any Google token.
INTERNAL_AUDIENCE = os.getenv("INTERNAL_AUDIENCE", "")
